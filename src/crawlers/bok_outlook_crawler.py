from src.crawlers.bok_minutes_crawler import BOKMinutesCrawler, NewsItem
import logging
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class BOKOutlookCrawler(BOKMinutesCrawler):
    """
    한국은행 경제전망 보고서 크롤러
    
    경제전망 보고서(Economic Outlook)를 찾아 GDP, CPI 전망치를 추출합니다.
    """
    
    # 경제전망/인플레이션 보고서 게시판 (보도자료 게시판과 공유될 수 있음)
    # 통화정책방향 결정문과 다르게 별도 게시판이나 보도자료를 검색해야 함.
    # 여기서는 보도자료 검색 기능을 활용.
    
    def get_latest_outlook_forecast(self, target_date: Optional[str] = None) -> Optional[Dict]:
        """
        가장 최근 경제전망 수치를 가져옵니다.
        
        Args:
            target_date: 이 날짜 이전의 최신 자료 검색 (YYYY-MM-DD or None)
            
        Returns:
            Dict containing release_date, forecasts (year -> {gdp, cpi})
        """
        if not target_date:
            target_date = datetime.now().strftime('%Y-%m-%d')
            
        # '경제전망' 키워드로 보도자료 검색 (조사국 또는 통화정책국)
        # 2025년 11월 경제전망과 같은 제목을 찾아야 함.
        # 메뉴번호 200690 (보도자료) 사용
        news_items = self.get_news_list(menu_no="200690", pages=3)
        
        outlook_items = []
        for item in news_items:
            # "경제전망" 포함하고 "수정" 포함하거나 포함하지 않거나 (수정 경제전망도 유효함)
            # 단, "설명회" 같은 건 제외할 수 있음. 제목에 "경제전망"이 명시적으로 있어야 함.
            if "경제전망" in item.title and "보도자료" not in item.title: 
                # 날짜 필터링
                if item.date <= target_date:
                    outlook_items.append(item)
                    
        if not outlook_items:
            logger.warning("최근 경제전망 자료를 찾을 수 없습니다.")
            return None
            
        # 최신 자료부터 파싱 시도
        outlook_items.sort(key=lambda x: x.date, reverse=True)
        
        for item in outlook_items:
            logger.info(f"경제전망 자료 파싱 시도: {item.title} ({item.date})")
            forecasts = self._parse_outlook_content(item.url)
            
            if forecasts:
                result = {
                    'release_date': item.date,
                    'description': item.title,
                    'source_url': item.url,
                    'forecasts': forecasts
                }
                return result
                
        return None

    def _parse_outlook_content(self, url: str) -> Optional[Dict]:
        """
        보도자료 본문에서 GDP, 물가 전망치 추출
        """
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 본문 추출
            content_div = soup.select_one('.dbData') or soup.select_one('.view_content')
            if not content_div:
                return None
                
            text = content_div.get_text(separator=' ', strip=True)
            
            # 정규표현식으로 추출
            # 예: "2025년 경제성장률은 1.9%, 소비자물가 상승률은 2.3%로 전망"
            forecasts = {}
            
            current_year = datetime.now().year
            years_to_find = [current_year, current_year + 1]
            
            for year in years_to_find:
                # GDP 찾기 (성장률 ... X.X%)
                # 패턴: (연도)? ... 성장률 ... (숫자)% 
                gdp_pattern = re.compile(f"{year}년.*?성장률.*?(\d+\.\d+)%")
                cpi_pattern = re.compile(f"{year}년.*?소비자물가.*?(\d+\.\d+)%")
                
                gdp_match = gdp_pattern.search(text)
                cpi_match = cpi_pattern.search(text)
                
                if gdp_match or cpi_match:
                    forecasts[year] = {
                        'gdp': float(gdp_match.group(1)) if gdp_match else None,
                        'cpi': float(cpi_match.group(1)) if cpi_match else None
                    }
            
            if not forecasts:
                # 테이블에서 추출 시도 등 추가 로직 필요할 수 있음
                pass
                
            return forecasts if forecasts else None
            
        except Exception as e:
            logger.error(f"본문 파싱 실패: {e}")
            return None

if __name__ == "__main__":
    # Test
    crawler = BOKOutlookCrawler()
    # print(crawler.get_latest_outlook_forecast())
