import enum


class UserRole(str, enum.Enum):
    customer = "customer"
    chef = "chef"
    admin = "admin"


class BookingStatus(str, enum.Enum):
    pending = "Pending"
    accepted = "Accepted"
    rejected = "Rejected"
    completed = "Completed"
    cancelled = "Cancelled"
