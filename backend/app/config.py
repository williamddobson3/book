"""Configuration settings for the booking system."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "sqlite:///./booking_system.db"
    
    # Login Credentials
    user_id: str = "84005565"
    password: str = "Bb1234567890"
    
    # API Settings
    base_url: str = "https://www.cm9.eprs.jp/shinagawa/web"
    api_timeout: int = 30
    
    # Browser Settings
    headless: bool = False  # Headful mode required for JS-heavy pages and browser checks
    browser_timeout: int = 120000  # Increased to 120 seconds for slow JS execution
    
    # Monitoring Settings
    poll_interval: int = 30
    intensive_poll_interval: float = 0.5
    
    # Target Parks
    target_parks: list[dict] = [
        {"bcd": "1040", "name": "しながわ区民公園", "area": "1200_1040", "priority": 1},
        {"bcd": "1010", "name": "しながわ中央公園", "area": "1400_1010", "priority": 2},
        {"bcd": "1030", "name": "八潮北公園", "area": "1500_1030", "priority": 3},
        {"bcd": "1020", "name": "東品川公園", "area": "1400_1020", "priority": 4},
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

