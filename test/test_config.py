import sys
sys.path.append('.')

from bot.utils.config import Config

print("🔍 Testing config loading...")
print(f"LARK_AUTHORIZED_USERS: {Config.LARK_AUTHORIZED_USERS}")
print(f"Is user authorized: {Config.is_user_authorized('HlbyGdJAqg-NsZwWL-lzlg')}")