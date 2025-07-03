import sys
sys.path.append('.')
from bot.utils.config import Config

# Test both versions
id_from_url = "HlbyGdJAqg-NsZwWL-lzlg"  # from URL (with 'l')
id_from_env = "HibyGdJAgq-NsZwWL-lzlg"  # from .env (with 'i')

print("🔍 Testing both IDs...")
print(f"Config loaded: {Config.LARK_AUTHORIZED_USERS}")
print(f"URL version (with 'l'): {Config.is_user_authorized(id_from_url)}")
print(f"ENV version (with 'i'): {Config.is_user_authorized(id_from_env)}")