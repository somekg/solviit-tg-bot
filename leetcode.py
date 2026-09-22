import requests
from typing import Optional, Dict, Any

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

# Combined GraphQL query for solve counts and contest stats
GRAPHQL_QUERY = """
query getUserLeetCodeStats($username: String!) {
  matchedUser(username: $username) {
    username
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
  }
  userContestRanking(username: $username) {
    rating
    globalRanking
    attendedContestsCount
  }
}
"""

def fetch_leetcode_stats(username: str) -> Optional[Dict[str, Any]]:
    """
    Fetches total solved, breakdown by difficulty (Easy, Medium, Hard),
    and contest rating for a given LeetCode handle.
    Returns None if the user does not exist or an error occurs.
    """
    headers = {
        "Content-Type": "application/json",
        "Referer": f"https://leetcode.com/{username}/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }
    
    payload = {
        "query": GRAPHQL_QUERY,
        "variables": {"username": username}
    }

    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            return None

        data = response.json()
        
        # LeetCode returns null for matchedUser if handle doesn't exist
        matched_user = data.get("data", {}).get("matchedUser")
        if not matched_user:
            return None

        # Parse submission numbers
        # submitStatsGlobal -> acSubmissionNum has entries:
        # [{"difficulty": "All", "count": X}, {"difficulty": "Easy", ...}, ...]
        sub_list = matched_user.get("submitStatsGlobal", {}).get("acSubmissionNum", [])
        
        counts = {item["difficulty"].lower(): item["count"] for item in sub_list}

        # Parse contest ranking (null if the user has never participated)
        contest_data = data.get("data", {}).get("userContestRanking")
        rating = round(contest_data.get("rating", 0.0), 1) if contest_data else 0.0
        global_rank = contest_data.get("globalRanking", 0) if contest_data else None

        return {
            "username": matched_user["username"],
            "total_solved": counts.get("all", 0),
            "easy_solved": counts.get("easy", 0),
            "medium_solved": counts.get("medium", 0),
            "hard_solved": counts.get("hard", 0),
            "contest_rating": rating,
            "global_ranking": global_rank
        }

    except requests.RequestException as e:
        print(f"Error fetching stats for {username}: {e}")
        return None


if __name__ == "__main__":
    # Quick manual test: replace with your handle or a known user like 'tourist'
    test_user = "neal_wu"
    print(f"Fetching stats for {test_user}...")
    stats = fetch_leetcode_stats(test_user)
    print(stats)