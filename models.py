from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, event
from sqlalchemy.engine import Engine
from sqlite3 import Connection as SQLite3Connection

# Create SQLAlchemy instance
db = SQLAlchemy()

# Enable SQLite Foreign Key Constraints
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Database models
class SMDPart(db.Model):
    __tablename__ = 'smd_part'
    
    id = db.Column(db.Integer, primary_key=True)
    part_number = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    digikey_number = db.Column(db.String(100), unique=True, nullable=False, index=True)  # Index for frequent searches
    quantity = db.Column(db.Integer, default=0)
    
    # Relationship to BOMEntry with Cascade-Delete
    bom_entries = db.relationship('BOMEntry', back_populates='smd_part', 
                                  cascade='all, delete-orphan', passive_deletes=True)
    
    def __repr__(self):
        return f"<SMDPart {self.part_number}>"
        
    def to_dict(self):
        """Converts the model to a dictionary"""
        return {
            'id': self.id,
            'part_number': self.part_number,
            'description': self.description,
            'digikey_number': self.digikey_number,
            'quantity': self.quantity
        }
    
    # Validation: Quantity must not be negative
    @db.validates('quantity')
    def validate_quantity(self, key, quantity):
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        return quantity

# Add index for part_number, but not unique, as duplicates may exist
Index('ix_smd_part_part_number', SMDPart.part_number)

class HardwareDevice(db.Model):
    __tablename__ = 'hardware_device'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)  # Index for frequent searches
    
    # Relationship to BOMEntry with Cascade-Delete
    bom_entries = db.relationship('BOMEntry', back_populates='hardware_device', 
                                  cascade='all, delete-orphan', passive_deletes=True)
    
    def __repr__(self):
        return f"<HardwareDevice {self.name}>"
        
    def to_dict(self):
        """Converts the model to a dictionary"""
        return {
            'id': self.id,
            'name': self.name
        }
    
    # Validation: Name must not be empty
    @db.validates('name')
    def validate_name(self, key, name):
        if not name or not name.strip():
            raise ValueError("Device name cannot be empty")
        return name.strip()

class BOMEntry(db.Model):
    __tablename__ = 'bom_entry'
    
    id = db.Column(db.Integer, primary_key=True)
    smd_part_id = db.Column(db.Integer, db.ForeignKey('smd_part.id', ondelete='CASCADE'), nullable=False)
    hardware_device_id = db.Column(db.Integer, db.ForeignKey('hardware_device.id', ondelete='CASCADE'), nullable=False)
    quantity_required = db.Column(db.Integer, nullable=False)

    # Define relationships
    smd_part = db.relationship('SMDPart', back_populates='bom_entries')
    hardware_device = db.relationship('HardwareDevice', back_populates='bom_entries')
    
    def __repr__(self):
        return f"<BOMEntry part_id={self.smd_part_id} device_id={self.hardware_device_id} qty={self.quantity_required}>"
    
    def to_dict(self):
        """Converts the model to a dictionary"""
        return {
            'id': self.id,
            'smd_part_id': self.smd_part_id,
            'hardware_device_id': self.hardware_device_id,
            'quantity_required': self.quantity_required
        }
    
    # Validation: Quantity must be positive
    @db.validates('quantity_required')
    def validate_quantity(self, key, quantity):
        if quantity <= 0:
            raise ValueError("Required quantity must be positive")
        return quantity

# Indexes for common access patterns
Index('ix_bom_entry_part_device', BOMEntry.smd_part_id, BOMEntry.hardware_device_id, unique=True)
Index('ix_bom_entry_device', BOMEntry.hardware_device_id)