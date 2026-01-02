from typing import List, Dict, Any, Optional

class Matcher:
    def __init__(self, playlists: List[Dict[str, Any]]):
        self.playlists = playlists

    def match(self, tags: Dict[str, float]) -> Optional[str]:
        """
        Finds the best matching playlist based on the aggregated tags.
        Score = Sum(Arbiter_Weight[tag]) for each tag in the playlist.
        Returns the name of the best playlist, or None if no suitable match found.
        """
        best_score = -1.0
        best_playlist = None

        for playlist in self.playlists:
            score = 0.0
            pl_tags = playlist.get("tags", [])
            
            # Calculate score: Sum of weights of tags present in the playlist
            # Only count tags that exist in our aggregated tags
            for tag in pl_tags:
                score += tags.get(tag, 0.0)
            
            # Debug print (can be removed later or moved to logging)
            # print(f"Playlist: {playlist.get('name')} Score: {score}")

            if score > best_score:
                best_score = score
                best_playlist = playlist.get("name")
        
        # If the best score is 0 or less, it means we didn't match any meaningful tags.
        # In this case, we might want to return None to indicate "keep current" or "no opinion".
        if best_score <= 0.001: # Use a small epsilon for float comparison
            return None
            
        return best_playlist
