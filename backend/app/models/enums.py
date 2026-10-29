from enum import StrEnum


class RequestStatus(StrEnum):
    SEARCHING = "searching"  # searching for riders
    GROUP_FOUND = "group_found"  # potential group found
    DRIVER_SEARCH = "driver_search"
    DRIVER_FOUND = "driver_found"
    CONFIRMED = "confirmed"
    DRIVER_ARRIVING = "driver_arriving"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TripStatus(StrEnum):
    OPEN = "open"
    MATCHED = "matched"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GroupStatus(StrEnum):
    FORMING = "forming"
    DRIVER_SEARCH = "driver_search"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class MatchStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RideStatus(StrEnum):
    CONFIRMED = "confirmed"
    DRIVER_ARRIVING = "driver_arriving"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    REQUIRES_CONFIRMATION = "requires_confirmation"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationStatus(StrEnum):
    UNSUBMITTED = "unsubmitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
