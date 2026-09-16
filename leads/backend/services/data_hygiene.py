import re

class DataHygieneService:
    @staticmethod
    def clean_name(name: str) -> str:
        if not name:
            return ""
        
        # Remove emojis and special chars (keep letters, spaces, hyphens)
        name = re.sub(r'[^\w\s\-]', '', name)
        
        # Remove common titles/suffixes
        titles = r'\b(mr|mrs|ms|dr|phd|md|prof)\b\.?'
        name = re.sub(titles, '', name, flags=re.IGNORECASE)
        
        # Fix ALL CAPS or all lower
        name = name.strip()
        if name.isupper() or name.islower():
            name = name.title()
            
        # Clean extra spaces
        name = re.sub(r'\s+', ' ', name)
        return name.strip()

    @staticmethod
    def clean_company(company: str) -> str:
        if not company:
            return ""
            
        # Remove legal entities
        entities = r'\b(llc|inc|corp|corporation|gmbh|ltd|limited|co)\b\.?'
        company = re.sub(entities, '', company, flags=re.IGNORECASE)
        
        # Remove emojis and weird punctuation (keep & and -)
        company = re.sub(r'[^\w\s\-\&]', '', company)
        
        # Fix ALL CAPS
        company = company.strip()
        if company.isupper():
            company = company.title()
            
        # Clean extra spaces
        company = re.sub(r'\s+', ' ', company)
        
        # Clean trailing hyphens or commas
        company = re.sub(r'[\-\,\&]$', '', company.strip())
        
        return company.strip()
