from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from markupsafe import escape
from flask_sqlalchemy import SQLAlchemy
import csv
import json
import pandas as pd
import io
import logging
import re
import os
import time
from werkzeug.utils import secure_filename
from sqlalchemy import text, distinct
import threading
import uuid

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

# Import own modules
from models import db, SMDPart, HardwareDevice, BOMEntry
from digikey_api import get_digikey_access_token, fetch_digikey_product_info, fetch_digikey_description, search_digikey_keyword, is_digikey_part_number, extract_product_data
from helpers import get_required_quantity, get_part_status_class, get_buildable_count, get_total_required_quantity, get_part_devices
from helpers import get_buildable_percentage, has_bom_entries, get_devices_with_bom
from helpers import get_unassigned_parts, count_unassigned_parts, has_unassigned_parts, is_part_unassigned

app = Flask(__name__)
# Use environment variable for database path or default
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///smd_inventory.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Set larger upload limits for CSV files
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Maximum file size limit
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Initialize database with the app
db.init_app(app)

# Global upload progress tracker
upload_progress = {}

# Template context processor for global functions
@app.context_processor
def utility_processor():
    return {
        'get_required_quantity': get_required_quantity,
        'get_part_status_class': get_part_status_class,
        'get_buildable_count': get_buildable_count,
        'get_total_required_quantity': get_total_required_quantity,
        'get_part_devices': get_part_devices,
        'get_buildable_percentage': get_buildable_percentage,
        'has_bom_entries': has_bom_entries,
        'get_devices_with_bom': get_devices_with_bom,
        'get_unassigned_parts': get_unassigned_parts,
        'count_unassigned_parts': count_unassigned_parts,
        'has_unassigned_parts': has_unassigned_parts,
        'is_part_unassigned': is_part_unassigned
    }

# Security function for validating user input
def validate_input(input_str, max_length=100, pattern=r'^[a-zA-Z0-9\-_.]+$'):
    """Validates and sanitizes user input"""
    if not input_str or not isinstance(input_str, str):
        return False, "Invalid input"
        
    # Length validation
    if len(input_str) > max_length:
        return False, f"Input too long (max. {max_length} characters)"
    
    # Pattern validation if specified
    if pattern and not re.match(pattern, input_str):
        return False, "Input contains invalid characters"
        
    return True, input_str

# Enhanced route for searching part numbers
@app.route('/search_digikey_by_mpn/<search_term>')
def search_digikey_by_mpn(search_term):
    """Searches for DigiKey part numbers or manufacturer part numbers, depending on what was entered"""
    try:
        # Validate the search term
        is_valid, result = validate_input(search_term, max_length=50, pattern=None)
        if not is_valid:
            return jsonify({"error": result}), 400
            
        logger.info(f"Search request for: {search_term}")
        # Check if the search term could be a DigiKey number
        is_dk_number = is_digikey_part_number(search_term)
        
        # First search in our local database
        if is_dk_number:
            # If it's a DigiKey number, search by this - parameterized query
            matching_parts = SMDPart.query.filter(
                SMDPart.digikey_number.ilike(f"%{search_term}%")
            ).all()
        else:
            # If it's a manufacturer number, search by this - parameterized query
            matching_parts = SMDPart.query.filter(
                SMDPart.part_number.ilike(f"%{search_term}%")
            ).all()
        
        local_results = []
        for part in matching_parts:
            local_results.append({
                'digikey_number': part.digikey_number,
                'part_number': part.part_number,
                'description': part.description
            })
        
        # If results found, return them directly
        if local_results:
            logger.info(f"Local results found: {len(local_results)}")
            return jsonify(local_results)
        
        # If no local results, query the DigiKey API
        api_products = search_digikey_keyword(search_term, 10)
        
        # Debug output for API response
        if api_products:
            logger.info(f"API products found: {len(api_products)}")
        
        api_results = []
        for product in api_products:
            # Use the new extraction function for consistent results
            digikey_number, manufacturer_number, description = extract_product_data(product)
            
            # Skip products without important information
            if not digikey_number and not manufacturer_number:
                continue
            
            # Ensure we have at least a minimal description
            if not description:
                description = "No description available"
            
            # Add the result to the list
            api_results.append({
                'digikey_number': digikey_number,
                'part_number': manufacturer_number,
                'description': description
            })
            
            # Debug output for each found product
            logger.info(f"Found product: DK={digikey_number}, MPN={manufacturer_number}")
        
        # If the product has variations (a manufacturer part with multiple DigiKey numbers),
        # also extract these as separate results
        for product in api_products:
            if 'ProductVariations' in product and product['ProductVariations']:
                manufacturer_number = product.get('ManufacturerProductNumber', product.get('ManufacturerPartNumber', ''))
                base_description = ""
                
                if 'Description' in product:
                    if isinstance(product['Description'], dict) and 'ProductDescription' in product['Description']:
                        base_description = product['Description']['ProductDescription']
                    else:
                        base_description = str(product['Description'])
                elif 'ProductDescription' in product:
                    base_description = product['ProductDescription']
                
                # Generate a result for each variation
                for variation in product['ProductVariations']:
                    if 'DigiKeyProductNumber' in variation:
                        digikey_number = variation['DigiKeyProductNumber']
                        package_type = ""
                        
                        if 'PackageType' in variation and 'Name' in variation['PackageType']:
                            package_type = variation['PackageType']['Name']
                        
                        # Only add if not already in results
                        is_duplicate = any(r['digikey_number'] == digikey_number for r in api_results)
                        
                        if not is_duplicate:
                            description = f"{base_description} ({package_type})" if package_type else base_description
                            
                            api_results.append({
                                'digikey_number': digikey_number,
                                'part_number': manufacturer_number,
                                'description': description
                            })
                            
                            logger.info(f"Added variation: DK={digikey_number}, MPN={manufacturer_number}, Type={package_type}")
        
        logger.info(f"API results prepared: {len(api_results)}")
        return jsonify(api_results)
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({"error": "Search could not be performed"}), 500

# Progress endpoint for CSV upload and processing
@app.route('/import-progress/<tracking_id>')
def import_progress(tracking_id):
    if tracking_id in upload_progress:
        return jsonify(upload_progress[tracking_id])
    return jsonify({"status": "unknown", "progress": 0, "message": "Unknown tracking ID"})

# BOM CSV Import
@app.route('/import_csv', methods=['POST'])
def import_csv():
    file = request.files.get('file')
    
    if not file:
        return redirect(url_for('index', error="No file selected"))
    
    # Initialize progress tracking
    tracking_id = str(uuid.uuid4())
    upload_progress[tracking_id] = {
        "status": "uploading", 
        "progress": 0,
        "message": "Uploading file...",
        "details": {}
    }
    
    # Check filename for security
    original_filename = secure_filename(file.filename)
    
    # Check file size
    file_content = file.read()
    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE:
        upload_progress[tracking_id]["status"] = "error"
        upload_progress[tracking_id]["message"] = f"File too large (max. {MAX_FILE_SIZE//1024//1024} MB)"
        return redirect(url_for('index', error=f"File too large (max. {MAX_FILE_SIZE//1024//1024} MB)", tracking_id=tracking_id))
    
    # Reset file pointer
    file.seek(0)
    
    try:
        # Process the CSV file
        if original_filename.lower().endswith('.csv'):
            upload_progress[tracking_id]["progress"] = 10
            upload_progress[tracking_id]["message"] = "Checking CSV file..."
            
            # Read the file and check if it's a BOM with Device information
            content = file_content.decode('utf-8', errors='replace')
            
            # Check if the Device line is present
            lines = content.splitlines()
            is_device_bom = False
            device_name = None
            
            for line in lines[:5]:  # Check the first few lines
                if line.lower().startswith('device,'):
                    is_device_bom = True
                    device_parts = line.split(',', 1)
                    if len(device_parts) > 1:
                        device_name = device_parts[1].strip()
                    break
            
            if not is_device_bom or not device_name:
                upload_progress[tracking_id]["status"] = "error"
                upload_progress[tracking_id]["message"] = "The BOM file doesn't contain a valid Device line (Device,Name)"
                return redirect(url_for('index', error="The BOM file doesn't contain a valid Device line (Device,Name)", tracking_id=tracking_id))
            
            # Validate the device name
            is_valid, result = validate_input(device_name, max_length=100, pattern=None)
            if not is_valid:
                upload_progress[tracking_id]["status"] = "error"
                upload_progress[tracking_id]["message"] = f"Invalid device name: {result}"
                return redirect(url_for('index', error=f"Invalid device name: {result}", tracking_id=tracking_id))
            
            upload_progress[tracking_id]["progress"] = 20
            upload_progress[tracking_id]["message"] = f"Preparing device '{device_name}'..."
            
            # Look for an existing device with this name or create a new one
            hardware_device = HardwareDevice.query.filter_by(name=device_name).first()
            if not hardware_device:
                # Create a new device
                hardware_device = HardwareDevice(name=device_name)
                db.session.add(hardware_device)
                db.session.commit()
                logger.info(f"Created new device: {device_name}")
            
            # Start BOM import as a thread to not block the UI
            upload_progress[tracking_id]["progress"] = 30
            upload_progress[tracking_id]["message"] = "Starting BOM import..."
            
            # Define the process-async function
            def process_async():
                # Create an application context for this thread
                with app.app_context():
                    try:
                        # BOM import
                        file.seek(0)
                        result, successful, failed = process_bom_csv(file, hardware_device, tracking_id)
                        
                        if result:
                            upload_progress[tracking_id]["status"] = "completed"
                            if failed:
                                upload_progress[tracking_id]["message"] = f"BOM for '{device_name}' imported with warnings. {successful} parts successful, {len(failed)} parts need attention."
                                upload_progress[tracking_id]["details"]["failed_parts"] = failed
                            else:
                                upload_progress[tracking_id]["message"] = f"BOM for '{device_name}' successfully imported. All {successful} parts were successfully entered."
                        else:
                            upload_progress[tracking_id]["status"] = "error"
                            upload_progress[tracking_id]["message"] = "Error importing the BOM."
                    except Exception as e:
                        logger.error(f"Background process error: {str(e)}")
                        upload_progress[tracking_id]["status"] = "error"
                        upload_progress[tracking_id]["message"] = f"Error: {str(e)}"
            
            # Start asynchronous processing
            thread = threading.Thread(target=process_async)
            thread.daemon = True
            thread.start()
            
            return redirect(url_for('index', info=f"Import for '{device_name}' started", tracking_id=tracking_id))
        else:
            upload_progress[tracking_id]["status"] = "error"
            upload_progress[tracking_id]["message"] = "Only CSV files are supported"
            return redirect(url_for('index', error="Only CSV files are supported", tracking_id=tracking_id))
    except UnicodeDecodeError:
        upload_progress[tracking_id]["status"] = "error"
        upload_progress[tracking_id]["message"] = "File contains invalid characters. Please save in UTF-8 format."
        return redirect(url_for('index', error="File contains invalid characters. Please save in UTF-8 format.", tracking_id=tracking_id))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Import error: {str(e)}")
        upload_progress[tracking_id]["status"] = "error"
        upload_progress[tracking_id]["message"] = f"Import error: {str(e)}"
        return redirect(url_for('index', error=f"Import error: {str(e)}", tracking_id=tracking_id))

def process_bom_csv(file, hardware_device, tracking_id=None):
    """Processes a BOM CSV file with semicolon or comma as separator"""
    try:
        # Read CSV file
        content = file.read().decode('utf-8', errors='replace').splitlines()
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 35
            upload_progress[tracking_id]["message"] = "Reading CSV file..."
        
        # Check for Device line and skip it
        start_row = 0
        for i, line in enumerate(content[:5]):
            if line.lower().startswith('device,'):
                start_row = i + 1
                break
        
        # Remove the Device line if present
        if start_row > 0:
            content = content[start_row:]
        
        # Try different separators, but prioritize semicolon
        delimiter = ';'
        # Check if comma is usable
        if content and ',' in content[0]:
            delimiter = ','
        
        # Validate CSV format
        if not content:
            raise ValueError("CSV file is empty")
            
        csv_reader = csv.reader([line for line in content if line.strip()], delimiter=delimiter)
        
        # Read the header row
        header = next(csv_reader, None)
        
        # Check if required columns are present
        if not header:
            raise ValueError("CSV file is empty or has no header row")
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 40
            upload_progress[tracking_id]["message"] = "Analyzing CSV headers..."
            
        # Find the indices for DigiKey number and quantity
        dk_index = None
        qty_index = None
        
        for i, col in enumerate(header):
            col_lower = col.lower().strip()
            if any(term in col_lower for term in ['digikey', 'digi-key', 'dk', 'dk-no']):
                dk_index = i
            elif any(term in col_lower for term in ['quantity', 'qty']):
                qty_index = i
        
        if dk_index is None or qty_index is None:
            raise ValueError("CSV file must contain columns for 'DigiKey Number' and 'Quantity'")
        
        # Read CSV data
        rows = list(csv_reader)
        total_rows = len(rows)
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 45
            upload_progress[tracking_id]["message"] = f"{total_rows} components found, beginning processing..."
            upload_progress[tracking_id]["details"]["total_parts"] = total_rows
            upload_progress[tracking_id]["details"]["processed_parts"] = 0
        
        # Prepare batch import of BOM entries
        parts_to_process = []   # Stores (part, quantity) pairs
        parts_to_add = []       # Parts to add to the database
        failed_parts = []       # Failed parts for reporting
        
        # Process the data
        for i, row in enumerate(rows):
            if len(row) <= max(dk_index, qty_index):
                continue  # Skip invalid rows
            
            digikey_number = row[dk_index].strip()
            
            # Skip empty DigiKey numbers
            if not digikey_number:
                continue
            
            # Update progress
            if tracking_id:
                progress_percent = 45 + (i / total_rows * 35)
                upload_progress[tracking_id]["progress"] = int(progress_percent)
                upload_progress[tracking_id]["message"] = f"Processing part {i+1} of {total_rows}: {digikey_number}..."
                upload_progress[tracking_id]["details"]["processed_parts"] = i + 1
            
            # Validate DigiKey number (pattern=None allows special characters like /)
            is_valid, result = validate_input(digikey_number, max_length=100, pattern=None)
            if not is_valid:
                logger.warning(f"Invalid digikey number: {digikey_number}, skipping")
                failed_parts.append({
                    "digikey_number": digikey_number,
                    "error": f"Invalid DigiKey number: {result}"
                })
                continue
            
            # Try to interpret the quantity as an integer
            try:
                quantity = int(row[qty_index].strip())
                if quantity <= 0:
                    logger.warning(f"Quantity must be positive for {digikey_number}, using default of 1")
                    quantity = 1  # Default to 1 instead of skipping
            except ValueError:
                # For invalid quantities, use default value
                logger.warning(f"Invalid quantity value for {digikey_number}, using default of 1")
                quantity = 1  # Default to 1
            
            # Collect BOM information with improved error handling
            result = process_bom_entry_batch(digikey_number, quantity, hardware_device.id)
            
            if result:
                part, is_new = result
                if is_new:
                    parts_to_add.append(part)
                
                # Add BOM entry for processing
                parts_to_process.append((part, quantity))
            else:
                # Part could not be processed - do NOT add to database anymore
                # Only store in the error list
                failed_parts.append({
                    "digikey_number": digikey_number,
                    "error": "Part could not be found via the DigiKey API"
                })
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 80
            upload_progress[tracking_id]["message"] = "Saving new parts to the database..."
        
        # Add parts individually to ensure IDs
        for part in parts_to_add:
            db.session.add(part)
            
        # Ensure all parts have an ID
        db.session.flush()
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 90
            upload_progress[tracking_id]["message"] = "Connecting parts to the device..."
        
        # Batch import of BOM entries
        if parts_to_process:
            # Delete existing BOM entries for this device
            BOMEntry.query.filter_by(hardware_device_id=hardware_device.id).delete()
            
            # Create new BOM entries - with additional checking
            entries_to_add = []
            for part, qty in parts_to_process:
                # Ensure part has an ID before creating a BOM entry
                if part.id is None:
                    logger.warning(f"Part {part.part_number} has no ID, skipping BOM entry for {part.digikey_number}")
                    continue
                
                entries_to_add.append(BOMEntry(
                    smd_part_id=part.id,
                    hardware_device_id=hardware_device.id,
                    quantity_required=qty
                ))
            
            # Add BOM entries individually to be safer
            for entry in entries_to_add:
                db.session.add(entry)
        
        # Commit all changes
        db.session.commit()
        
        if tracking_id:
            upload_progress[tracking_id]["progress"] = 100
            
        # Return: success, number of successful parts, list of failed parts
        return True, len(parts_to_process) - len(failed_parts), failed_parts
    except Exception as e:
        db.session.rollback()
        logger.error(f"CSV processing error: {str(e)}")
        if tracking_id:
            upload_progress[tracking_id]["status"] = "error"
            upload_progress[tracking_id]["message"] = f"Error processing CSV: {str(e)}"
        raise e

def create_error_part_entry(digikey_number):
    """Creates a database entry for a part that could not be found"""
    return SMDPart(
        part_number=f"MANUAL-SEARCH-{digikey_number}",
        description=f"⚠️ ERROR: Part not found - {digikey_number} - Please search manually",
        digikey_number=digikey_number,
        quantity=0  # Initial stock is 0
    )

def process_bom_entry_batch(digikey_number, quantity, hardware_device_id):
    """Prepares a BOM entry for batch import"""
    
    # Skip empty entries
    if not digikey_number or digikey_number == "nan":
        return None
    
    # Check if part exists in database
    smd_part = SMDPart.query.filter_by(digikey_number=digikey_number).first()
    
    if not smd_part:
        # If not, create a new part with info from DigiKey API
        if is_digikey_part_number(digikey_number):
            try:
                manufacturer_part_number, description = fetch_digikey_product_info(digikey_number)
                if not manufacturer_part_number:
                    manufacturer_part_number = digikey_number  # Fallback
                
                smd_part = SMDPart(
                    part_number=manufacturer_part_number,
                    description=description or "No description available",
                    digikey_number=digikey_number,
                    quantity=0  # Initial stock is 0
                )
                
                return (smd_part, True)  # Part and flag for new creation
            except Exception as e:
                logger.error(f"Error fetching part {digikey_number}: {str(e)}")
                return None  # Error retrieving, handled in the main handler
    
    return (smd_part, False) if smd_part else None  # Part and flag for existing

# Home page
@app.route('/')
def index():
    smd_parts = SMDPart.query.all()
    hardware_devices = HardwareDevice.query.all()
    devices_with_bom = get_devices_with_bom()
    unassigned_parts = get_unassigned_parts()
    
    # Read parameters from URL
    tracking_id = request.args.get('tracking_id')
    
    return render_template('base.html', 
                          smd_parts=smd_parts, 
                          hardware_devices=hardware_devices, 
                          devices_with_bom=devices_with_bom,
                          unassigned_parts=unassigned_parts,
                          tracking_id=tracking_id)

# Update SMD stock
@app.route('/update_stock', methods=['POST'])
def update_stock():
    try:
        # Either part_id (from modal) or digikey_number (from form)
        if 'part_id' in request.form:
            # Update an existing part
            part_id = request.form.get('part_id')
            new_quantity = request.form.get('quantity')
            
            # Validate part_id
            try:
                part_id = int(part_id)
            except (ValueError, TypeError):
                return "Invalid component ID", 400
                
            # Validate quantity
            try:
                new_quantity = int(new_quantity)
                if new_quantity < 0:
                    return "Quantity must not be negative", 400
            except (ValueError, TypeError):
                return "Invalid quantity", 400
            
            smd_part = SMDPart.query.get(part_id)
            if smd_part:
                smd_part.quantity = new_quantity
                db.session.commit()
        else:
            # New structure with search form
            digikey_number = request.form.get('digikey_number', '').strip()
            manufacturer_part_number = request.form.get('part_number', '').strip()
            
            # Validate input data
            is_valid, result = validate_input(digikey_number, max_length=100, pattern=None)
            if not is_valid:
                return f"Invalid DigiKey number: {result}", 400
                
            is_valid, result = validate_input(manufacturer_part_number, max_length=100, pattern=None)
            if not is_valid:
                return f"Invalid manufacturer number: {result}", 400
            
            # Validate quantity
            try:
                quantity = int(request.form.get('quantity', 0))
                if quantity < 0:
                    return "Quantity must not be negative", 400
            except (ValueError, TypeError):
                return "Invalid quantity", 400
                
            description = request.form.get('description', '')
            
            # New function: Device assignment
            device_ids = request.form.getlist('usage')
            
            # Validate device_ids
            valid_device_ids = []
            for device_id in device_ids:
                try:
                    device_id = int(device_id)
                    # Check if the device exists
                    if HardwareDevice.query.get(device_id):
                        valid_device_ids.append(device_id)
                except (ValueError, TypeError):
                    # Skip invalid IDs
                    continue
            
            # New function: Device-specific quantities
            device_quantities = {}
            if 'device_quantities' in request.form:
                try:
                    device_quantities = json.loads(request.form.get('device_quantities', '{}'))
                    # Validate device_quantities
                    validated_quantities = {}
                    for device_id, qty in device_quantities.items():
                        try:
                            device_id = str(int(device_id))  # Convert to int and back to str
                            qty = int(qty)
                            if qty > 0:
                                validated_quantities[device_id] = qty
                        except (ValueError, TypeError):
                            continue
                    device_quantities = validated_quantities
                except (json.JSONDecodeError, ValueError, TypeError):
                    logger.error("Error parsing device quantities")
                    device_quantities = {}
            
            logger.info(f"Form data: DK={digikey_number}, MPN={manufacturer_part_number}, Qty={quantity}, Devices={valid_device_ids}, DeviceQty={device_quantities}")
            
            if not digikey_number:
                return "Error: No DigiKey number provided", 400
            
            # Check if this number already exists in the database
            smd_part = SMDPart.query.filter_by(digikey_number=digikey_number).first()
            
            if smd_part:
                # Update existing part
                logger.info(f"Existing part found: {smd_part.part_number} / {smd_part.digikey_number}")
                smd_part.quantity = quantity
                
                # Also update description and manufacturer number if provided
                if description:
                    smd_part.description = description
                
                if manufacturer_part_number and manufacturer_part_number != smd_part.part_number:
                    smd_part.part_number = manufacturer_part_number
            else:
                # Add new part
                logger.info(f"Adding new part: DigiKey={digikey_number}, MPN={manufacturer_part_number}")
                
                # If no description provided, try to get it from the API
                if not description and is_digikey_part_number(digikey_number):
                    fetched_mpn, fetched_description = fetch_digikey_product_info(digikey_number)
                    
                    if fetched_description:
                        description = fetched_description
                    
                    if fetched_mpn and not manufacturer_part_number:
                        manufacturer_part_number = fetched_mpn
                
                # Fallback: If still no manufacturer number is available
                if not manufacturer_part_number:
                    manufacturer_part_number = digikey_number
                
                new_part = SMDPart(
                    part_number=manufacturer_part_number,
                    description=description or "No description available",
                    digikey_number=digikey_number,
                    quantity=quantity
                )
                
                db.session.add(new_part)
                db.session.flush()  # To generate the ID
                smd_part = new_part
            
            # Update device assignments
            if valid_device_ids:
                # Check existing assignments and update
                existing_entries = {entry.hardware_device_id: entry for entry in 
                                  BOMEntry.query.filter_by(smd_part_id=smd_part.id).all()}
                
                entries_to_update = []
                entries_to_add = []
                
                for device_id in valid_device_ids:
                    # Get required quantity for this device from device_quantities
                    required_qty = 1  # Default value
                    if str(device_id) in device_quantities:
                        required_qty = device_quantities[str(device_id)]
                    
                    # Check if the assignment already exists
                    if device_id in existing_entries:
                        # Update existing assignment
                        existing_entries[device_id].quantity_required = required_qty
                        entries_to_update.append(existing_entries[device_id])
                    else:
                        # Create new assignment
                        new_bom = BOMEntry(
                            smd_part_id=smd_part.id,
                            hardware_device_id=device_id,
                            quantity_required=required_qty
                        )
                        entries_to_add.append(new_bom)
                
                # Batch update and insert
                if entries_to_update:
                    db.session.bulk_save_objects(entries_to_update)
                
                if entries_to_add:
                    db.session.bulk_save_objects(entries_to_add)
            
            db.session.commit()
    
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_stock: {str(e)}")
        return f"Error updating stock: {str(e)}", 500

# New endpoint for updating part usage
@app.route('/update_part_usage', methods=['POST'])
def update_part_usage():
    try:
        # Validate input data
        try:
            part_id = int(request.form.get('part_id'))
            device_id = int(request.form.get('device_id'))
            qty_required = int(request.form.get('qty_required', 0))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid parameter values'}), 400
        
        if qty_required < 0:
            return jsonify({'success': False, 'message': 'Quantity must not be negative'}), 400
        
        # Check if part and device exist
        smd_part = SMDPart.query.get(part_id)
        hardware_device = HardwareDevice.query.get(device_id)
        
        if not smd_part or not hardware_device:
            return jsonify({'success': False, 'message': 'Part or device not found'}), 404
        
        # Update or create BOM entry
        bom_entry = BOMEntry.query.filter_by(
            smd_part_id=part_id, 
            hardware_device_id=device_id
        ).first()
        
        if bom_entry:
            # If quantity is 0, delete the entry
            if qty_required <= 0:
                db.session.delete(bom_entry)
            else:
                bom_entry.quantity_required = qty_required
        else:
            # Only create if quantity > 0
            if qty_required > 0:
                new_bom = BOMEntry(
                    smd_part_id=part_id,
                    hardware_device_id=device_id,
                    quantity_required=qty_required
                )
                db.session.add(new_bom)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Usage updated',
            'new_qty': qty_required
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating part usage: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# Get missing parts for a model (API endpoint)
@app.route('/missing_parts/<int:device_id>')
def missing_parts(device_id):
    try:
        # Validate device_id
        hardware_device = HardwareDevice.query.get_or_404(device_id)
        
        # All BOM entries for this device - Optimized query
        entries_with_parts = db.session.query(
            BOMEntry, SMDPart
        ).join(
            SMDPart, BOMEntry.smd_part_id == SMDPart.id
        ).filter(
            BOMEntry.hardware_device_id == device_id
        ).all()
        
        missing_parts = []
        for entry, part in entries_with_parts:
            if part.quantity < entry.quantity_required:
                missing_parts.append({
                    'part_number': part.part_number,
                    'description': part.description,
                    'required': entry.quantity_required,
                    'available': part.quantity,
                    'missing': entry.quantity_required - part.quantity
                })
        
        # Sort by missing stock in descending order
        missing_parts.sort(key=lambda x: x['missing'], reverse=True)
        
        return jsonify({
            'device_name': hardware_device.name,
            'missing_parts': missing_parts
        })
    except Exception as e:
        logger.error(f"Error getting missing parts: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Delete function for SMD parts
@app.route('/delete_part/<int:part_id>', methods=['POST'])
def delete_part(part_id):
    try:
        # Validate part_id
        part = SMDPart.query.get_or_404(part_id)
        
        # First delete the BOM entries (foreign key relationship)
        BOMEntry.query.filter_by(smd_part_id=part_id).delete()
        
        # Then delete the part itself
        db.session.delete(part)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Part successfully deleted'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting part: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting: {str(e)}'}), 500

# DigiKey API Test Route (for testing the API connection)
@app.route('/test_api/<digikey_number>')
def test_api(digikey_number):
    try:
        # Validate digikey_number
        is_valid, result = validate_input(digikey_number, max_length=100, pattern=None)
        if not is_valid:
            return jsonify({'error': result}), 400
            
        manufacturer_part_number, description = fetch_digikey_product_info(digikey_number)
        return jsonify({
            'description': description,
            'manufacturer_part_number': manufacturer_part_number
        })
    except Exception as e:
        logger.error(f"API test error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# New route for adding devices
@app.route('/add_device', methods=['POST'])
def add_device():
    try:
        device_name = request.form.get('device_name', '').strip()
        
        # Validate the device name
        is_valid, result = validate_input(device_name, max_length=100, pattern=None)
        if not is_valid:
            return jsonify({'success': False, 'message': f'Invalid device name: {result}'})
        
        if device_name:
            # Check if the device already exists
            existing_device = HardwareDevice.query.filter_by(name=device_name).first()
            if existing_device:
                return jsonify({'success': False, 'message': 'A device with this name already exists'})
            
            # Create new device
            new_device = HardwareDevice(name=device_name)
            db.session.add(new_device)
            db.session.commit()
            
            return jsonify({'success': True, 'device_id': new_device.id, 'device_name': new_device.name})
        
        return jsonify({'success': False, 'message': 'No device name provided'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Add device error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# New route for deleting devices
@app.route('/delete_device/<int:device_id>', methods=['POST'])
def delete_device(device_id):
    try:
        # Check if the device exists
        device = HardwareDevice.query.get_or_404(device_id)
        
        # First delete all BOM entries for this device
        # This causes components to become unassigned if they were only used for this device
        BOMEntry.query.filter_by(hardware_device_id=device_id).delete()
        
        # Then delete the device itself
        db.session.delete(device)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Device "{device.name}" successfully deleted'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete device error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting: {str(e)}'}), 500

# New route for editing device names
@app.route('/update_device_name', methods=['POST'])
def update_device_name():
    try:
        # Validate input data
        try:
            device_id = int(request.form.get('device_id'))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid device ID'}), 400
            
        new_name = request.form.get('new_name', '').strip()
        
        # Validate the new name
        is_valid, result = validate_input(new_name, max_length=100, pattern=None)
        if not is_valid:
            return jsonify({'success': False, 'message': f'Invalid device name: {result}'})
        
        if not new_name:
            return jsonify({'success': False, 'message': 'No new name provided'}), 400
        
        # Find device
        device = HardwareDevice.query.get_or_404(device_id)
        
        # Check if the new name already exists
        existing = HardwareDevice.query.filter_by(name=new_name).first()
        if existing and existing.id != device_id:
            return jsonify({'success': False, 'message': 'A device with this name already exists'})
        
        # Update name
        device.name = new_name
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Device name updated', 'new_name': new_name})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update device name error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        db.session.commit()
        
    # Control debug mode via environment variable
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)