"""
예측 모델 모듈

- 금리 결정 확률 예측 (Logit)
- 자산 가격 영향 분석 (VAR)
"""
from .rate_predictor import RatePredictor

__all__ = ['RatePredictor']
