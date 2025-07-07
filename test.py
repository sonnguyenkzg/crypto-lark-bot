#!/usr/bin/env python3
"""
test.py
This script sends a table-formatted message to a Lark (Feishu) group chat.
It uses an incoming webhook URL to post the message.

To use this script:
1.  Replace 'YOUR_WEBHOOK_URL' with your actual Lark bot's incoming webhook URL.
2.  Run the script: python test.py
"""
import requests
import json
import time
from typing import Dict, Any

# --- Configuration ---
# IMPORTANT: Replace with your actual webhook URL
WEBHOOK_URL = "https://vigilant-waffle-97xq59vgwgvjf979q-8080.app.github.dev"

def create_table_message_payload() -> Dict[str, Any]:
    """
    Creates the JSON payload for a message card containing a native table component.
    This structure is based on the official Lark documentation for interactive cards.
    Ref: https://open.larksuite.com/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components/content-components/table
    """
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "Wallet Balance Report"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Here is the latest balance report for the requested wallets."
                    }
                },
                # This is the native table component, which is more robust than a markdown table.
                {
                    "tag": "table",
                    "data": {
                        "header": [
                            {
                                "text": {
                                    "tag": "plain_text",
                                    "content": "Group"
                                }
                            },
                            {
                                "text": {
                                    "tag": "plain_text",
                                    "content": "Wallet Name"
                                }
                            },
                            {
                                "text": {
                                    "tag": "plain_text",
                                    "content": "Amount (USDT)"
                                }
                            }
                        ],
                        "rows": [
                            [
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "Trading"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "Binance-Hot-1"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "1,234,567.89"
                                    }
                                }
                            ],
                            [
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "Treasury"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "Cold-Storage-A"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "9,876,543.21"
                                    }
                                }
                            ],
                            [
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "Operations"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "OKX-Ops"
                                    }
                                },
                                {
                                    "text": {
                                        "tag": "plain_text",
                                        "content": "500,000.00"
                                    }
                                }
                            ]
                        ]
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "Last updated: " + time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    ]
                }
            ]
        }
    }
    return payload

def send_lark_message(payload: Dict[str, Any]):
    """
    Sends the given payload to the Lark webhook URL.
    """
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(WEBHOOK_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        
        response_json = response.json()
        if response_json.get("StatusCode") == 0 or response_json.get("code") == 0:
            print("✅ Message sent successfully!")
            print("Response:", response_json)
        else:
            print("❌ Failed to send message.")
            print("Response:", response_json)

    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred while sending the request: {e}")
    except json.JSONDecodeError:
        print("❌ Failed to decode JSON from response.")
        print("Raw response:", response.text)


if __name__ == "__main__":
    if "YOUR_WEBHOOK_URL" in WEBHOOK_URL:
        print("⚠️ Please replace 'YOUR_WEBHOOK_URL' with your actual Lark webhook URL in the script.")
    else:
        print("🚀 Creating and sending table message...")
        message_payload = create_table_message_payload()
        send_lark_message(message_payload)
