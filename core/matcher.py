import numpy as np
from typing import List, Dict, Any, Optional

class Matcher:
    def __init__(self, playlists: List[Dict[str, Any]]):
        self.playlists = playlists

    def match(self, tags: Dict[str, float]) -> Optional[str]:
        """
        Finds the best matching playlist based on the aggregated tags.
        Uses Cosine Similarity with NumPy.
        
        Returns the name of the best playlist, or None if no suitable match found.
        """
        if not tags:
            return None

        # 1. Identify the Universe of Tags
        # We need to consider all tags present in the current environment AND in the playlists
        # to construct proper vectors.
        env_tags = set(tags.keys())
        playlist_tags_union = set()
        for pl in self.playlists:
            playlist_tags_union.update(pl.get("tags", []))
        
        # Sort to ensure consistent indexing
        all_tags = sorted(list(env_tags | playlist_tags_union))
        tag_to_index = {tag: i for i, tag in enumerate(all_tags)}
        dim = len(all_tags)

        # 2. Create Environment Vector
        v_env = np.zeros(dim)
        for tag, weight in tags.items():
            if tag in tag_to_index:
                v_env[tag_to_index[tag]] = weight
        
        # Calculate magnitude of env vector
        norm_env = np.linalg.norm(v_env)
        if norm_env < 1e-6:
            return None

        best_score = -1.0
        best_playlist = None

        # 3. Compare with each Playlist
        for playlist in self.playlists:
            pl_tags_list = playlist.get("tags", [])
            if not pl_tags_list:
                continue
            
            # Create Playlist Vector
            v_pl = np.zeros(dim)
            for tag in pl_tags_list:
                if tag in tag_to_index:
                    v_pl[tag_to_index[tag]] = 1.0 # Binary weight for playlist tags
            
            norm_pl = np.linalg.norm(v_pl)
            if norm_pl < 1e-6:
                continue

            # Cosine Similarity
            dot_product = np.dot(v_env, v_pl)
            similarity = dot_product / (norm_env * norm_pl)
            
            # Debug print (can be removed later or moved to logging)
            # print(f"Playlist: {playlist.get('name')} Sim: {similarity:.4f}")

            if similarity > best_score:
                best_score = similarity
                best_playlist = playlist.get("name")
        
        if best_score <= 0.001: 
            return None
            
        return best_playlist
