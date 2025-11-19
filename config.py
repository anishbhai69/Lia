import os

# টোকেনটি এখন os.getenv থেকে লোড হবে
TOKEN = os.getenv("DISCORD_BOT_TOKEN") 

# যদি টোকেন না পাওয়া যায়
if not TOKEN:
    print("❌ WARNING: DISCORD_BOT_TOKEN environment variable not set.")
