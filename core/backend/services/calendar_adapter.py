from typing import List, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

class CalendarProviderAdapter(ABC):
    @abstractmethod
    async def get_availability(self, start_date: str, end_date: str, timezone: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def create_booking(self, lead_email: str, lead_name: str, start_time: str, end_time: str) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    async def cancel_booking(self, booking_id: str) -> bool:
        pass

class CalComAdapter(CalendarProviderAdapter):
    def __init__(self, token: str, link: str):
        self.token = token
        self.link = link
        
    async def get_availability(self, start_date: str, end_date: str, timezone: str) -> List[Dict[str, Any]]:
        # Mock realistic availability
        return [
            {"start_time": "2024-03-25T14:00:00Z", "end_time": "2024-03-25T14:30:00Z"},
            {"start_time": "2024-03-26T10:00:00Z", "end_time": "2024-03-26T10:30:00Z"}
        ]
        
    async def create_booking(self, lead_email: str, lead_name: str, start_time: str, end_time: str) -> Dict[str, Any]:
        return {"booking_id": "mock_calcom_123", "status": "confirmed"}
        
    async def cancel_booking(self, booking_id: str) -> bool:
        return True

class CalendlyAdapter(CalendarProviderAdapter):
    def __init__(self, token: str, link: str):
        self.token = token
        self.link = link
        
    async def get_availability(self, start_date: str, end_date: str, timezone: str) -> List[Dict[str, Any]]:
        # Mock realistic availability
        return [
            {"start_time": "2024-03-25T15:00:00Z", "end_time": "2024-03-25T15:30:00Z"},
            {"start_time": "2024-03-27T11:00:00Z", "end_time": "2024-03-27T11:30:00Z"}
        ]
        
    async def create_booking(self, lead_email: str, lead_name: str, start_time: str, end_time: str) -> Dict[str, Any]:
        return {"booking_id": "mock_calendly_123", "status": "confirmed"}
        
    async def cancel_booking(self, booking_id: str) -> bool:
        return True

def get_calendar_adapter(account_data: dict) -> CalendarProviderAdapter:
    """Factory function to get the right adapter based on the account's provider setting."""
    provider = account_data.get("calendar_provider")
    token = account_data.get("calendar_token", "")
    link = account_data.get("calendar_link", "")
    
    if provider == "cal.com":
        return CalComAdapter(token, link)
    elif provider == "calendly":
        return CalendlyAdapter(token, link)
    return None
