with open("publisher/meta_graph_api.py", "r", encoding="utf-8") as f:
    content = f.read()

methods = """
    @classmethod
    def discover_instagram_accounts(cls, user_access_token: str, version: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Auto-discovers all connected Facebook Pages and linked Instagram Business/Creator
        accounts from a single Meta User Access Token.
        """
        v = version or settings.META_GRAPH_VERSION
        url = f"https://graph.facebook.com/{v}/me/accounts"
        params = {
            "fields": "id,name,access_token,category,instagram_business_account{id,username,name,profile_picture_url,followers_count}",
            "limit": 100,
            "access_token": user_access_token
        }
        discovered = []
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                data = res.json()
                for page in data.get("data", []):
                    page_id = page.get("id")
                    page_name = page.get("name")
                    page_token = page.get("access_token") or user_access_token
                    ig_acc = page.get("instagram_business_account")
                    if ig_acc and ig_acc.get("id"):
                        username = ig_acc.get("username", "")
                        discovered.append({
                            "id": username.replace(".", "_") if username else f"ig_{ig_acc['id']}",
                            "handle": f"@{username}" if username else f"@ig_{ig_acc['id']}",
                            "display_name": ig_acc.get("name") or page_name,
                            "niche": "Tech & Science",
                            "ig_user_id": str(ig_acc["id"]),
                            "access_token": page_token,
                            "avatar_initials": (username[:2] if username else "IG").upper(),
                            "brand_color": "#f97316",
                            "followers": ig_acc.get("followers_count", 0),
                            "fb_page_name": page_name,
                            "is_active": 1
                        })
            else:
                logger.warning(f"Meta discovery error: {res.status_code} - {res.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to discover Instagram accounts: {e}")
        return discovered

    @classmethod
    def test_token_validity(cls, access_token: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Tests whether an access token is valid and inspects its profile info.
        """
        if not access_token:
            return {"valid": False, "error": "No token provided"}
        v = version or settings.META_GRAPH_VERSION
        try:
            me_url = f"https://graph.facebook.com/{v}/me"
            res = requests.get(me_url, params={"fields": "id,name", "access_token": access_token}, timeout=10)
            if res.status_code == 200:
                me_data = res.json()
                return {
                    "valid": True,
                    "id": me_data.get("id"),
                    "name": me_data.get("name"),
                    "type": "PAGE_OR_USER_TOKEN",
                    "status": "ACTIVE"
                }
            else:
                err_msg = res.json().get("error", {}).get("message", res.text[:150])
                return {"valid": False, "error": err_msg}
        except Exception as e:
            return {"valid": False, "error": str(e)}
"""

if "discover_instagram_accounts" not in content:
    if "from typing import " in content and "List" not in content:
        content = content.replace("from typing import ", "from typing import List, ")
    content += "\n" + methods
    with open("publisher/meta_graph_api.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Methods appended successfully!")
else:
    print("Already exists!")
