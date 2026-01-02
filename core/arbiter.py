from typing import List, Dict, Any
from core.policies import Policy

class Arbiter:
    def __init__(self, policies: List[Policy]):
        self.policies = policies

    def arbitrate(self, context: Dict[str, Any]) -> Dict[str, float]:
        """
        Aggregates tags from all policies based on the given context.
        Returns a dictionary of tags and their summed weights.
        """
        aggregated_tags: Dict[str, float] = {}
        for policy in self.policies:
            try:
                tags = policy.get_tags(context)
                for tag, weight in tags.items():
                    aggregated_tags[tag] = aggregated_tags.get(tag, 0.0) + weight
            except Exception as e:
                print(f"Error in policy {type(policy).__name__}: {e}")
                
        return aggregated_tags
