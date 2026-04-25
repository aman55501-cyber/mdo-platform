"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HdfcConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HDFC_")

    api_key: str = ""
    api_secret: str = ""
    redirect_url: str = "http://localhost:8080/callback"
    base_url: str = "https://developer.hdfcsec.com"
    static_ip: str = ""
    max_orders_per_sec: int = 10


class GrokConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROK_")

    api_key: str = ""
    base_url: str = "https://api.x.ai/v1"
    # Live search (/v1/responses Agent Tools) only works with grok-4 family.
    # Standard model for sentiment polling + portfolio watch
    model: str = "grok-4"
    # Fast model for high-frequency polls (Singhvi every 5 min)
    # Use a lighter grok-4 variant if available, else same as model
    model_fast: str = "grok-4"
    # Deep model for on-demand analysis (/grok command, morning overview)
    model_deep: str = "grok-4"
    # Enable real-time X + news search via Agent Tools (/v1/responses)
    live_search: bool = True
    poll_interval_seconds: int = 180
    max_tool_budget: float = 0.10


class TelegramConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    bot_token: str = ""
    chat_id: str = ""
    alert_chat_id: str | None = None


class StrategyConfig(BaseSettings):
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    risk_per_trade_pct: float = Field(default=2.0, alias="RISK_PER_TRADE_PCT")
    max_positions: int = Field(default=5, alias="MAX_POSITIONS")
    daily_loss_limit_pct: float = Field(default=5.0, alias="DAILY_LOSS_LIMIT_PCT")
    target_pct: float = Field(default=3.0, alias="TARGET_PCT")
    stop_loss_pct: float = Field(default=1.5, alias="STOP_LOSS_PCT")

    model_config = SettingsConfigDict(populate_by_name=True)


class DashboardConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_")

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8501


class VegaConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hdfc: HdfcConfig = Field(default_factory=HdfcConfig)
    grok: GrokConfig = Field(default_factory=GrokConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    watchlist: list[str] = Field(
        default=["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
        alias="WATCHLIST",
    )
    db_path: str = Field(default="vega_data.db", alias="DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @classmethod
    def load(cls) -> VegaConfig:
        from dotenv import load_dotenv

        load_dotenv()
        return cls(
            hdfc=HdfcConfig(),
            grok=GrokConfig(),
            telegram=TelegramConfig(),
            strategy=StrategyConfig(),
            dashboard=DashboardConfig(),
        )
