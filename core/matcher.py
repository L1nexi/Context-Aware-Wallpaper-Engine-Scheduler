import math
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("WEScheduler.Matcher")

# Minimum cosine similarity to consider a match valid.
# Below this threshold the environment vector is too orthogonal to all
# playlists to produce a meaningful selection.
_MIN_SIMILARITY = 0.001

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
            v = [0.0] * self.dim
            tags = pl.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = 1.0
            elif isinstance(tags, dict):
                for tag, weight in tags.items():
                    if tag in self.tag_to_index:
                        v[self.tag_to_index[tag]] = weight
            
            norm = math.sqrt(sum(x * x for x in v))
            if norm > 1e-6:
                v = [x / norm for x in v]
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
        v_env = [0.0] * self.dim
        for tag, weight in tags.items():
            if tag in self.tag_to_index:
                v_env[self.tag_to_index[tag]] = weight
        
        norm_env = math.sqrt(sum(x * x for x in v_env))
        if norm_env < 1e-6:
            return None
        
        v_env = [x / norm_env for x in v_env]

        best_score = -1.0
        best_playlist = None

        # 4. Compare with each Playlist Vector
        for name, v_pl in self.playlist_vectors:
            # Since both are normalized, dot product is cosine similarity
            similarity = sum(a * b for a, b in zip(v_env, v_pl))
            
            if similarity > best_score:
                best_score = similarity
                best_playlist = name
        
        if best_score <= _MIN_SIMILARITY:
            return None
            
        return best_playlist
