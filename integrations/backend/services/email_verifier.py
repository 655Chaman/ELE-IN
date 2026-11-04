import smtplib
import os
import socket
import uuid
try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    dns = None
    HAS_DNS = False
import re
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

ENABLE_DIRECT_SMTP_VERIFICATION = os.getenv("ENABLE_DIRECT_SMTP_VERIFICATION", "").lower() in ("true", "1")

class EmailVerifier:
    """
    Zero-Cost Discovery Engine (Email Permutation & SMTP Verification)
    Replaces paid providers by generating permutations and doing raw SMTP handshakes.
    """
    
    @staticmethod
    def generate_permutations(first_name: str, last_name: str, domain: str) -> List[str]:
        import unicodedata
        
        # Clean unicode (e.g., "José" -> "jose", "O'Connor" -> "oconnor")
        def clean_str(s: str) -> str:
            s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
            return re.sub(r'[^a-zA-Z0-9]', '', s).lower()
            
        f = clean_str(first_name)
        l = clean_str(last_name)
        
        # Strip URL protocols/paths if a raw URL was passed
        d = domain.lower().strip()
        d = re.sub(r'^https?://', '', d)
        d = re.sub(r'^www\.', '', d)
        d = d.split('/')[0]
        
        if not f or not l or not d:
            return []
            
        return [
            f"{f}.{l}@{d}",    # first.last
            f"{f}{l}@{d}",     # firstlast
            f"{f}@{d}",        # first
            f"{f[0]}{l}@{d}",  # flast
            f"{f}{l[0]}@{d}",  # firstl
            f"{f[0]}.{l}@{d}", # f.last
            f"{l}@{d}"         # last
        ]

    @staticmethod
    def get_mx_record(domain: str) -> Optional[str]:
        if not domain:
            return None
        if HAS_DNS and dns:
            try:
                records = dns.resolver.resolve(domain, 'MX')
                mx_record = sorted(records, key=lambda x: x.preference)[0].exchange.to_text()
                return mx_record
            except Exception as e:
                logger.warning(f"MX lookup failed for {domain}: {e}")
                return None
        # Safe fallback to standard socket resolution if dnspython is absent
        try:
            import socket
            socket.gethostbyname(domain)
            return domain
        except Exception as e:
            logger.warning(f"Fallback host resolution failed for {domain}: {e}")
            return None


    @staticmethod
    def verify_email_smtp(email: str, mx_record: str) -> bool:
        """
        Layer 1 Paranoia: Direct SMTP verification over port 25 is blocked by major cloud
        providers (AWS, GCP, Render) and direct connections without proper rDNS will be flagged.
        Guarded by ENABLE_DIRECT_SMTP_VERIFICATION.
        Uses verified host configuration instead of spoofing third-party ESP domains.
        """
        enabled = os.getenv("ENABLE_DIRECT_SMTP_VERIFICATION", "").lower() in ("true", "1")
        if not enabled:
            logger.debug(f"[EmailVerifier] Direct SMTP handshake skipped for {email} (ENABLE_DIRECT_SMTP_VERIFICATION is off).")
            return False

        try:
            with smtplib.SMTP(mx_record, 25, timeout=10) as smtp:
                helo_host = os.getenv("SMTP_HELO_HOST") or socket.getfqdn() or "mail.elein.ai"
                verify_sender = os.getenv("SMTP_VERIFY_SENDER") or f"verify@{helo_host}"
                smtp.helo(helo_host)
                smtp.mail(f"<{verify_sender}>")
                code, message = smtp.rcpt(email)
                # 250 means OK
                # 251 means user not local but will forward
                if code in (250, 251):
                    return True
                return False
        except Exception as e:
            logger.warning(f"SMTP verify failed for {email} via {mx_record}: {e}")
            # False negative preferred over false positive
            return False

    @classmethod
    def discover_email(cls, first_name: str, last_name: str, domain: str) -> Optional[str]:
        """
        Generates permutations and finds the first valid email.
        """
        if not domain:
            return None
            
        mx_record = cls.get_mx_record(domain)
        if not mx_record:
            return None
            
        # Paranoia Layer 2: Catch-All Domain Detection
        # If a random gibberish email returns True, the domain is a catch-all. 
        # We cannot verify ANY email on a catch-all domain reliably via SMTP.
        catch_all_test = f"test_chk_{uuid.uuid4().hex[:12]}@{domain}"
        if cls.verify_email_smtp(catch_all_test, mx_record):
            logger.info(f"Domain {domain} is a catch-all. SMTP verification is impossible.")
            return None
            
        perms = cls.generate_permutations(first_name, last_name, domain)
        for email in perms:
            if cls.verify_email_smtp(email, mx_record):
                logger.info(f"Successfully discovered valid email: {email}")
                return email
                
        return None

    @classmethod
    def verify_email(cls, email: str) -> bool:
        """
        Verify if an email is valid by checking syntax, MX record, and SMTP handshake.
        Layer 1 & 2 Paranoia:
        - Validate regex syntax first.
        - Resolve MX records.
        - Detect catch-all domains.
        - Execute SMTP verification with timeout and fail-safe fallback.
        """
        if not email or not isinstance(email, str):
            return False
        clean_email = email.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean_email):
            return False
        parts = clean_email.split("@")
        if len(parts) != 2:
            return False
        domain = parts[1].strip()
        mx_record = cls.get_mx_record(domain)
        if not mx_record:
            return False
        
        # Catch-all check
        catch_all_test = f"xyz_elein_test_123456789@{domain}"
        if cls.verify_email_smtp(catch_all_test, mx_record):
            # Domain accepts anything -> cannot verify single address via SMTP, but MX exists
            return True
        return cls.verify_email_smtp(clean_email, mx_record)

