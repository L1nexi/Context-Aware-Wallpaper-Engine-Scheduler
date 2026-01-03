import numpy as np
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("WEScheduler.Matcher")

class Matcher:
    def __init__(self, playlists: List[Dict[str, Any]]):
        self.playlists = playlists
        # 1. Identify the Universe of Tags from all playlists
        self.all_tags = set()
        for pl in self.playlists:
            tags = pl.get("tags", [])
            if isinstance(tags, list):
                self.all_tags.update(tags)
            elif isinstance(tags, dict):
                self.all_tags.update(tags.keys())
        
        self.all_tags = sorted(list(self.all_tags))
        self.tag_to_index = {tag: i for i, tag in enumerate(self.all_tags)}
        self.dim = len(self.all_tags)

        # 2. Pre-calculate Normalized Playlist Vectors
        self.playlist_vectors = []
        for pl in self.playlists:
            v = np.zeros(self.dim)
            tags = pl.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = 1.0
            elif isinstance(tags, dict):
                for tag, weight in tags.items():
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = weight
            
            norm = np.linalg.norm(v)
            if norm > 1e-6:
                v = v / norm
                self.playlist_vectors.append((pl.get("name"), v))
            else:
                logger.warning(f"Playlist '{pl.get('name')}' has no valid tags or zero weights.")

    def match(self, tags: Dict[str, float]) -> Optional[str]:
        """
        Finds the best matching playlist based on the aggregated tags.
        Uses Cosine Similarity with pre-calculated vectors.
        """
        if not tags or not self.playlist_vectors:
            return None

        # 3. Create Normalized Environment Vector
        v_env = np.zeros(self.dim)
        for tag, weight in tags.items():
            if tag in self.tag_to_index:
                v_env[self.tag_to_index[tag]] = weight
        
        norm_env = np.linalg.norm(v_env)
        if norm_env < 1e-6:
            return None
        
        v_env = v_env / norm_env

        best_score = -1.0
        best_playlist = None

        # 4. Compare with each Playlist Vector
        for name, v_pl in self.playlist_vectors:
            # Since both are normalized, dot product is cosine similarity
            similarity = np.dot(v_env, v_pl)
            
            if similarity > best_score:
                best_score = similarity
                best_playlist = name
        
        if best_score <= 0.001: 
            return None
            
        return best_playlist
