class AnonymizationError(Exception):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthorizationError(Exception):
    def __init__(self, message: str, required_permission: str = None):
        super().__init__(message)
        self.message = message
        self.required_permission = required_permission


class PolicyNotFoundError(Exception):
    def __init__(self, entity_type: str, org_id: str):
        super().__init__(f"No policy found for entity type '{entity_type}' in org '{org_id}'")
        self.entity_type = entity_type
        self.org_id = org_id


class TokenNotFoundError(Exception):
    def __init__(self, token: str, org_id: str):
        super().__init__(f"Token '{token}' not found in org '{org_id}'")
        self.token = token
        self.org_id = org_id


class TokenExpiredError(Exception):
    def __init__(self, token: str, org_id: str):
        super().__init__(f"Token '{token}' has expired in org '{org_id}'")
        self.token = token
        self.org_id = org_id