import unittest
import sys
import os
import time
import math
from datetime import datetime

# 将项目根目录加入路径，确保能导入 core 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.matcher import Matcher
from core.policies import TimePolicy

class TestMatcher(unittest.TestCase):
    def setUp(self):
        # 模拟播放列表配置
        self.playlists = [
            { "name": "PURE_WORK", "tags": { "#work": 1.0 } },
            { "name": "MIXED_CHILL", "tags": { "#chill": 1.0, "#night": 0.5 } }, # 偏向 chill，但也带点 night
            { "name": "PURE_NIGHT", "tags": { "#night": 1.0 } }
        ]
        self.matcher = Matcher(self.playlists)

    def test_exact_match(self):
        """测试精确匹配"""
        # 环境完全是 #work
        env_tags = {"#work": 1.0}
        result = self.matcher.match(env_tags)
        self.assertEqual(result, "PURE_WORK")

    def test_vector_similarity(self):
        """测试向量相似度：混合场景"""
        # 环境是 #chill (1.0) 和 #night (1.0)
        # 理论上应该匹配 MIXED_CHILL 或 PURE_NIGHT，取决于角度
        # MIXED_CHILL 向量: <chill:1, night:0.5> -> 归一化后 <0.89, 0.44>
        # PURE_NIGHT 向量: <night:1> -> <0, 1>
        # 环境向量: <chill:1, night:1> -> <0.707, 0.707>
        
        # 计算点积:
        # vs MIXED: 0.89*0.707 + 0.44*0.707 ≈ 0.63 + 0.31 = 0.94
        # vs NIGHT: 0 * 0.707 + 1 * 0.707 = 0.707
        # 结论：应该匹配 MIXED_CHILL
        
        env_tags = {"#chill": 1.0, "#night": 1.0}
        result = self.matcher.match(env_tags)
        self.assertEqual(result, "MIXED_CHILL")

    def test_noise_filtering(self):
        """测试噪声过滤（正交性）"""
        # 环境是 #game，播放列表里没有 #game，应该返回 None
        env_tags = {"#game": 1.0}
        result = self.matcher.match(env_tags)
        self.assertIsNone(result)

class TestTimePolicy(unittest.TestCase):
    def setUp(self):
        self.config = {
            "enabled": True,
            "weight_scale": 1.0,
            "day_start": 8,  # 08:00
            "night_start": 20 # 20:00
        }
        self.policy = TimePolicy(self.config)

    def _mock_context(self, hour, minute=0):
        # 构造一个伪造的时间上下文
        mock_time = time.struct_time((2024, 1, 1, hour, minute, 0, 0, 1, -1))
        return {"time": mock_time}

    def test_deep_night(self):
        """测试深夜 (02:00)"""
        context = self._mock_context(2)
        tags = self.policy.get_tags(context)
        # 应该只有 #night，且权重很高
        self.assertIn("#night", tags)
        self.assertNotIn("#day", tags)
        self.assertAlmostEqual(tags["#night"], 1.0, delta=0.1)

    def test_noon(self):
        """测试正午 (14:00)"""
        context = self._mock_context(14)
        tags = self.policy.get_tags(context)
        self.assertIn("#day", tags)
        self.assertNotIn("#night", tags)

    def test_sunset_interpolation(self):
        """测试黄昏插值 (20:00)"""
        # 正好在 night_start，应该有 #sunset 且可能有 #night/#day 的过渡
        context = self._mock_context(20)
        tags = self.policy.get_tags(context)
        
        # 必须包含 sunset
        self.assertIn("#sunset", tags)
        
        # 验证归一化：模长应该接近 1.0 * weight_scale
        norm = math.sqrt(sum(w * w for w in tags.values()))
        self.assertAlmostEqual(norm, 1.0, delta=0.01)

if __name__ == '__main__':
    unittest.main()
