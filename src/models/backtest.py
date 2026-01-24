
import pandas as pd
import numpy as np
import logging
from typing import List, Dict
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.rate_predictor import RatePredictor, PredictionResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class Backtester:
    """
    금리 예측 모델 백테스터 (Walk-Forward Validation)
    """
    
    def __init__(self, start_idx: int = 10):
        """
        Args:
            start_idx: 학습을 시작할 최소 데이터 개수. 이 시점 이후부터 예측을 수행함.
        """
        self.predictor = RatePredictor()
        self.start_idx = start_idx
        self.results = []
        
    def run(self):
        """백테스트 실행"""
        # 1. 데이터 로드
        try:
            df = self.predictor.load_tone_data()
        except FileNotFoundError:
            logger.error("데이터 파일을 찾을 수 없습니다.")
            return

        # 2. 날짜순 정렬
        if 'meeting_date' not in df.columns:
            df['meeting_date'] = pd.to_datetime(df['meeting_date_str'].str.replace('_', '-'))
        df = df.sort_values('meeting_date').reset_index(drop=True)
        
        # 3. 레이블이 있는 데이터만 필터링
        labeled_df = []
        for _, row in df.iterrows():
            if row['meeting_date_str'] in self.predictor.RATE_HISTORY:
                labeled_df.append(row)
        
        df_labeled = pd.DataFrame(labeled_df).reset_index(drop=True)
        
        logger.info(f"총 데이터 수: {len(df)}, 레이블이 있는 데이터 수: {len(df_labeled)}")
        logger.info(f"백테스트 시작 (초기 학습 데이터: {self.start_idx}개)")
        print("-" * 80)
        print(f"{'회의일':<12} {'실제':<6} {'예측':<6} {'정확':<4} {'신뢰도':<8} {'Tone':<8} {'상태'}")
        print("-" * 80)

        # 4. Walk-Forward Loop
        correct_count = 0
        total_count = 0
        
        for i in range(self.start_idx, len(df_labeled)):
            # 학습 데이터 (과거 데이터)
            train_df = df_labeled.iloc[:i]
            
            # 테스트 데이터 (현재 예측 대상)
            test_row = df_labeled.iloc[i]
            target_date = test_row['meeting_date_str']
            
            # 실제 결과
            rate, actual_action_code = self.predictor.RATE_HISTORY[target_date]
            actual_action = self.predictor.ACTION_LABELS[self.predictor.ACTION_MAP[actual_action_code]]
            
            # 모델 학습
            # 주의: 매번 새로운 인스턴스를 만들지 않고 train을 다시 호출하여 리셋됨을 이용
            # scaler가 fit_transform으로 매번 갱신되므로 정보 유출 없음
            self.predictor = RatePredictor() 
            self.predictor.train(train_df)
            
            # 예측
            pred_result = self.predictor.predict(test_row.to_dict())
            
            # 결과 기록
            is_correct = (pred_result.predicted_action == actual_action)
            if is_correct:
                correct_count += 1
            total_count += 1
            
            self.results.append({
                'date': target_date,
                'actual': actual_action,
                'predicted': pred_result.predicted_action,
                'is_correct': is_correct,
                'confidence': pred_result.confidence,
                'tone': test_row['tone_index'],
                'probs': [pred_result.prob_hike, pred_result.prob_hold, pred_result.prob_cut]
            })
            
            # 출력
            mark = "O" if is_correct else "X"
            print(f"{target_date:<12} {actual_action:<6} {pred_result.predicted_action:<6} {mark:<4} {pred_result.confidence:.1%}    {test_row['tone_index']:+.3f}")

        # 5. 최종 리포트
        accuracy = correct_count / total_count if total_count > 0 else 0
        print("-" * 80)
        print(f"백테스트 완료")
        print(f"총 예측: {total_count}회")
        print(f"정답: {correct_count}회")
        print(f"정확도: {accuracy:.2%}")
        
        self.plot_results()
        
    def plot_results(self):
        """결과 시각화 (터미널 환경이라 저장은 생략하거나 파일로 저장)"""
        if not self.results:
            return
            
        # 결과 DataFrame
        res_df = pd.DataFrame(self.results)
        
        # 정확도 추이 (누적)
        res_df['cumulative_acc'] = res_df['is_correct'].expanding().mean()
        
        print("\n[구간별 정확도]")
        # 5개씩 묶어서 정확도 확인
        chunk_size = 5
        for i in range(0, len(res_df), chunk_size):
            chunk = res_df.iloc[i:i+chunk_size]
            acc = chunk['is_correct'].mean()
            start_date = chunk.iloc[0]['date']
            end_date = chunk.iloc[-1]['date']
            print(f"{start_date} ~ {end_date}: {acc:.2%}")

if __name__ == "__main__":
    backtester = Backtester(start_idx=10) # 최소 10개의 데이터로 시작
    backtester.run()
