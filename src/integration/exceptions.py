class IntegrationException(Exception):
    """Base exception for integration layer errors."""
    pass


# AWS EC2 Specific Exceptions

class EC2Exception(IntegrationException):
    """Base exception for AWS EC2 related errors."""
    pass


class EC2InstanceNotFoundException(EC2Exception):
    """Raised when an EC2 instance is not found."""
    pass


class EC2InstanceCreationException(EC2Exception):
    """Raised when EC2 instance creation fails."""
    pass


class EC2InstanceOperationException(EC2Exception):
    """Raised when an EC2 instance operation (start/stop/terminate) fails."""
    pass


class EC2TagOperationException(EC2Exception):
    """Raised when an EC2 tag operation fails."""
    pass


class EC2StatusCheckException(EC2Exception):
    """Raised when retrieving EC2 status checks fails."""
    pass


class EC2AuthenticationException(EC2Exception):
    """Raised when AWS credentials are invalid or insufficient permissions."""
    pass


class EC2QuotaExceededException(EC2Exception):
    """Raised when AWS resource quota/limit is exceeded."""
    pass


class EC2InvalidParameterException(EC2Exception):
    """Raised when invalid parameters are provided to AWS API."""
    pass
