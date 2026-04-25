"""Custom exception hierarchy for VEGA."""


class VegaError(Exception):
    """Base exception for all VEGA errors."""


class BrokerError(VegaError):
    """Error communicating with the broker API."""


class AuthenticationError(BrokerError):
    """Authentication failed or session expired."""


class OrderError(BrokerError):
    """Order placement/modification/cancellation failed."""


class RateLimitError(BrokerError):
    """API rate limit exceeded."""


class SentimentError(VegaError):
    """Error in sentiment analysis pipeline."""


class StrategyError(VegaError):
    """Error in strategy evaluation."""


class RiskLimitError(VegaError):
    """Risk limit breached - trade rejected."""
