from models import BOMEntry, SMDPart, HardwareDevice
from sqlalchemy import func, distinct
from sqlalchemy.orm import joinedload

# Helper functions for templates
def get_required_quantity(part_id, device_id):
    """Determines the required quantity of a component for a specific hardware model"""
    if not part_id or not device_id:
        return 0
        
    entry = BOMEntry.query.filter_by(smd_part_id=part_id, hardware_device_id=device_id).first()
    return entry.quantity_required if entry else 0

def get_part_status_class(part):
    """Returns the CSS class for the component status (ok, low, missing)"""
    if not part:
        return ""
        
    # Check if the part is needed for any model
    entries = BOMEntry.query.filter_by(smd_part_id=part.id).all()
    
    if not entries:
        return ""  # Neutral if not needed
    
    # Check all entries at once
    has_missing = False
    has_low = False
    
    for entry in entries:
        if entry.quantity_required <= 0:
            continue  # Ignore invalid entries
            
        if part.quantity < entry.quantity_required:
            has_missing = True
            break  # Break immediately, as Missing status has priority
        elif part.quantity < entry.quantity_required * 2:
            has_low = True
            # Continue checking if there are missing parts
    
    if has_missing:
        return "part-status-missing"  # Red if not enough for at least one model
    elif has_low:
        return "part-status-low"  # Yellow if low
    
    return "part-status-ok"  # Green if sufficient

def get_buildable_count(device_id):
    """Calculates how many units of a hardware model can be built"""
    if not device_id:
        return "N/A"
        
    # Query all BOM entries for this device - optimized query
    entries_with_parts = BOMEntry.query.filter_by(hardware_device_id=device_id)\
                          .join(SMDPart, BOMEntry.smd_part_id == SMDPart.id)\
                          .with_entities(BOMEntry.quantity_required, SMDPart.quantity)\
                          .all()
    
    if not entries_with_parts:
        return "N/A"
    
    # Initial value for buildable
    buildable = None
    
    # Calculate possible units for each entry
    for required, available in entries_with_parts:
        if required <= 0:
            continue  # Skip invalid entries
            
        units_possible = available // required
        
        # Update buildable (minimum of possible units)
        if buildable is None:
            buildable = units_possible
        else:
            buildable = min(buildable, units_possible)
    
    return buildable if buildable is not None else 0

def get_buildable_percentage(device_id):
    """Calculates the percentage of completion based on available parts"""
    if not device_id:
        return 0
        
    # Optimized query with fewer roundtrips to the database
    entries_with_parts = BOMEntry.query.filter_by(hardware_device_id=device_id)\
                          .join(SMDPart, BOMEntry.smd_part_id == SMDPart.id)\
                          .with_entities(BOMEntry.quantity_required, SMDPart.quantity)\
                          .all()
    
    if not entries_with_parts:
        return 0  # If no BOM entries exist
    
    total_percentage = 0
    components_count = 0
    
    for required, available in entries_with_parts:
        if required <= 0:
            continue  # Skip invalid entries
            
        component_percentage = min(100, (available / required) * 100)
        total_percentage += component_percentage
        components_count += 1
    
    if components_count == 0:
        return 0
        
    average_percentage = total_percentage / components_count
    return round(min(100, average_percentage))

def has_bom_entries(device_id):
    """Checks if BOM entries exist for a device"""
    if not device_id:
        return False
        
    return BOMEntry.query.filter_by(hardware_device_id=device_id).count() > 0

def get_devices_with_bom():
    """Returns all devices that have BOM entries - optimized query"""
    # Distinct device_ids that appear in BOMEntry
    device_ids_query = BOMEntry.query.with_entities(distinct(BOMEntry.hardware_device_id)).all()
    device_ids = [entry[0] for entry in device_ids_query]
    
    if not device_ids:
        return []
    
    # Retrieve devices
    return HardwareDevice.query.filter(HardwareDevice.id.in_(device_ids)).all()

def get_unassigned_parts():
    """Returns all components that are not assigned to any device (don't have a BOM entry)"""
    # Identify components that don't have a BOM entry - optimized query
    assigned_part_ids_query = BOMEntry.query.with_entities(distinct(BOMEntry.smd_part_id)).all()
    assigned_part_ids = [entry[0] for entry in assigned_part_ids_query]
    
    # If no parts are assigned, return all parts
    if not assigned_part_ids:
        return SMDPart.query.all()
    
    # Otherwise, return only the unassigned parts
    return SMDPart.query.filter(~SMDPart.id.in_(assigned_part_ids)).all()

def count_unassigned_parts():
    """Counts the number of components that are not assigned to any device - optimized query"""
    # Subquery for assigned parts
    assigned_parts_subquery = BOMEntry.query.with_entities(distinct(BOMEntry.smd_part_id)).subquery()
    
    # Count parts that are not in the subquery
    count_query = SMDPart.query.filter(~SMDPart.id.in_(assigned_parts_subquery)).count()
    
    return count_query

def has_unassigned_parts():
    """Checks if there are components that are not assigned to any device - optimized query"""
    # More efficient to only check if there is at least one unassigned part
    return count_unassigned_parts() > 0

def get_part_devices(part_id):
    """Returns a list of all devices in which a part is used - optimized query"""
    if not part_id:
        return []
        
    # Optimized query with eager loading
    entries = BOMEntry.query.filter_by(smd_part_id=part_id)\
                     .options(joinedload(BOMEntry.hardware_device))\
                     .all()
    
    devices = []
    for entry in entries:
        if entry.hardware_device:  # Ensure the device exists
            devices.append({
                'device_id': entry.hardware_device_id,
                'device_name': entry.hardware_device.name,
                'qty_required': entry.quantity_required
            })
    
    return devices

def get_total_required_quantity(part_id):
    """Calculates the total quantity of a component needed across all devices - optimized query"""
    if not part_id:
        return 0
        
    # Calculate sum with a SQL query
    total = BOMEntry.query.filter_by(smd_part_id=part_id)\
                   .with_entities(func.sum(BOMEntry.quantity_required))\
                   .scalar()
    
    return total or 0  # Convert None to 0 if no entries exist

def is_part_unassigned(part_id):
    """Checks if a component is not assigned to any device - optimized query"""
    if not part_id:
        return True
        
    return BOMEntry.query.filter_by(smd_part_id=part_id).count() == 0