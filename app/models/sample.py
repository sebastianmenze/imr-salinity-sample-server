from sqlalchemy import Column, String, Float, DateTime, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid
import enum


class SampleStatus(str, enum.Enum):
    registered = "registered"   # Label printed, sample bottle filled
    in_lab = "in_lab"           # QR scanned in lab
    measured = "measured"       # Lab salinity entered
    uploaded = "uploaded"       # Pushed to PhysChem


class SalinitySample(Base):
    __tablename__ = "salinity_samples"

    # Primary key — becomes the QR code URL path
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Oceanographic metadata (from BOT file or manual entry)
    utc_time = Column(DateTime(timezone=True), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    depth_m = Column(Float, nullable=False)
    platform_id = Column(String(100), nullable=False)
    cruise_id = Column(String(50), nullable=True)
    station_id = Column(String(50), nullable=True)
    cast_number = Column(String(20), nullable=True)
    bottle_number = Column(String(20), nullable=True)

    # CTD sensor salinities (from BOT file)
    psal_1 = Column(Float, nullable=True)
    psal_2 = Column(Float, nullable=True)

    # Lab measurement
    psal_lab = Column(Float, nullable=True)
    measured_by = Column(String(100), nullable=True)
    measured_at = Column(DateTime(timezone=True), nullable=True)

    # System fields
    status = Column(SAEnum(SampleStatus), default=SampleStatus.registered, nullable=False)
    notes = Column(Text, nullable=True)
    physchem_upload_id = Column(String(100), nullable=True)   # reading ID returned by PhysChem
    physchem_operation_id = Column(String(50), nullable=True)  # PhysChem operation (CTD cast) ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    source = Column(String(20), default="manual")  # "manual" or "bot_file"

    @property
    def psal_diff(self):
        if self.psal_1 is not None and self.psal_2 is not None:
            return round(abs(self.psal_1 - self.psal_2), 4)
        return None

    @property
    def label_url(self):
        from app.config import settings
        return f"{settings.base_url}/measure/{self.id}"

    def __repr__(self):
        return f"<SalinitySample {self.id} {self.platform_id} {self.utc_time}>"
