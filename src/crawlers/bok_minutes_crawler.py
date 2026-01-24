"""
한국은행 금융통화위원회 의사록 크롤러

한국은행 홈페이지에서 금융통화위원회 통화정책방향 결정회의 의사록을 수집합니다.
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field, asdict
from typing import Optional
import time
import logging
import re
import json
from datetime import datetime
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MinutesItem:
    """의사록 게시물 정보"""
    meeting_date: str
    meeting_number: Optional[int] = None
    year: Optional[int] = None
    decision_url: Optional[str] = None
    press_url: Optional[str] = None
    minutes_url: Optional[str] = None
    minutes_hwp_url: Optional[str] = None
    minutes_pdf_url: Optional[str] = None
    issue_url: Optional[str] = None


@dataclass
class NewsItem:
    """뉴스/보도자료 게시물 정보"""
    title: str
    date: str
    url: str
    department: Optional[str] = None
    views: Optional[int] = None


class BOKMinutesCrawler:
    """한국은행 금융통화위원회 의사록 크롤러"""

    BASE_URL = "https://www.bok.or.kr"

    # 통화정책방향 결정회의 페이지 (연도별 의사록 제공)
    POLICY_MEETING_URL = "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do"

    # 뉴스/자료 페이지 (AJAX 엔드포인트)
    NEWS_LIST_URL = "https://www.bok.or.kr/portal/singl/newsData/listCont.do"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.bok.or.kr/'
        })

    def fetch_policy_meeting_page(self, year: Optional[int] = None) -> Optional[str]:
        """
        통화정책방향 결정회의 페이지를 가져옵니다.

        Args:
            year: 조회할 연도 (None이면 현재 연도)

        Returns:
            HTML 문자열 또는 None (실패시)
        """
        params = {
            'mtgSe': 'A',  # A: 전체, B: 정기, C: 임시
            'menuNo': '200755',
        }

        if year:
            params['pYear'] = str(year)

        try:
            logger.info(f"통화정책방향 결정회의 페이지 요청 중... (연도: {year or '현재'})")
            response = self.session.get(self.POLICY_MEETING_URL, params=params, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except requests.RequestException as e:
            logger.error(f"페이지 요청 실패: {e}")
            return None

    def parse_policy_meeting_page(self, html: str, year: Optional[int] = None) -> list[MinutesItem]:
        """
        통화정책방향 결정회의 페이지에서 의사록 정보를 파싱합니다.

        Args:
            html: HTML 문자열
            year: 연도

        Returns:
            MinutesItem 리스트
        """
        soup = BeautifulSoup(html, 'html.parser')
        items = []

        # 테이블에서 데이터 추출
        table = soup.select_one('#tableId, table.tb-type01, table')
        if not table:
            logger.warning("테이블을 찾을 수 없습니다")
            return items

        rows = table.select('tbody tr')
        logger.info(f"발견된 회의 행: {len(rows)}개")

        for row in rows:
            item = self._parse_meeting_row(row, year)
            if item:
                items.append(item)

        return items

    def _parse_meeting_row(self, row, year: Optional[int] = None) -> Optional[MinutesItem]:
        """개별 회의 행을 파싱합니다."""
        try:
            # 날짜는 th 태그에 있음
            th = row.select_one('th')
            cells = row.select('td')

            if not th or len(cells) < 4:
                return None

            date_text = th.get_text(strip=True)

            # 날짜 패턴 추출 (예: "01월 15일(목)")
            date_match = re.search(r'(\d{1,2})월\s*(\d{1,2})일', date_text)
            if not date_match:
                return None

            month = int(date_match.group(1))
            day = int(date_match.group(2))

            # 유효한 날짜인지 확인
            if month < 1 or month > 12 or day < 1 or day > 31:
                return None

            if year:
                meeting_date = f"{year}.{month:02d}.{day:02d}"
            else:
                meeting_date = f"{month:02d}.{day:02d}"

            item = MinutesItem(meeting_date=meeting_date, year=year)

            # 각 셀에서 링크 추출
            # 셀 순서 (th 제외): 결정문[0], 기자간담회[1], 의사록[2], 금융·경제 이슈[3]
            if len(cells) > 0:
                decision_link = cells[0].select_one('a[href*="fileDown.do"]')
                if decision_link:
                    item.decision_url = self._make_full_url(decision_link.get('href', ''))

            if len(cells) > 1:
                press_link = cells[1].select_one('a[href*="fileDown.do"]')
                if press_link:
                    item.press_url = self._make_full_url(press_link.get('href', ''))

            if len(cells) > 2:
                # 의사록 셀에서 HWP/PDF 링크 추출
                minutes_cell = cells[2]

                # fileDown.do 링크 찾기
                all_links = minutes_cell.select('a[href*="fileDown.do"]')
                for link in all_links:
                    href = link.get('href', '')
                    link_text = link.get_text(strip=True).upper()
                    if 'HWP' in link_text:
                        item.minutes_hwp_url = self._make_full_url(href)
                    elif 'PDF' in link_text:
                        item.minutes_pdf_url = self._make_full_url(href)
                    elif not item.minutes_url:
                        item.minutes_url = self._make_full_url(href)

            if len(cells) > 3:
                issue_link = cells[3].select_one('a[href*="fileDown.do"]')
                if issue_link:
                    item.issue_url = self._make_full_url(issue_link.get('href', ''))

            return item

        except Exception as e:
            logger.debug(f"회의 행 파싱 실패: {e}")
            return None

    def _make_full_url(self, href: str) -> str:
        """상대 URL을 절대 URL로 변환합니다."""
        if not href:
            return ''
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            return self.BASE_URL + href
        return self.BASE_URL + '/' + href

    def get_minutes_by_year(self, year: int) -> list[MinutesItem]:
        """
        특정 연도의 의사록 목록을 수집합니다.

        Args:
            year: 연도

        Returns:
            MinutesItem 리스트
        """
        html = self.fetch_policy_meeting_page(year=year)
        if html:
            return self.parse_policy_meeting_page(html, year=year)
        return []

    def get_minutes_list(self, years: list[int] = None, delay: float = 1.0) -> list[MinutesItem]:
        """
        여러 연도의 의사록 목록을 수집합니다.

        Args:
            years: 수집할 연도 목록 (None이면 현재 연도만)
            delay: 요청 간 대기 시간(초)

        Returns:
            MinutesItem 리스트
        """
        if years is None:
            years = [datetime.now().year]

        all_items = []

        for i, year in enumerate(years):
            items = self.get_minutes_by_year(year)
            all_items.extend(items)
            logger.info(f"{year}년: {len(items)}개 회의 수집")

            if i < len(years) - 1:
                time.sleep(delay)

        return all_items

    # === 뉴스/보도자료 크롤링 (의사록 관련 보도자료) ===

    def fetch_news_page(self, menu_no: str = "200789", page_index: int = 1, page_unit: int = 10) -> Optional[str]:
        """
        뉴스/보도자료 목록 페이지를 가져옵니다.

        Args:
            menu_no: 메뉴 번호 (200789: 의사록, 200690: 통화정책 보도자료)
            page_index: 페이지 번호
            page_unit: 페이지당 게시물 수

        Returns:
            HTML 문자열 또는 None (실패시)
        """
        params = {
            'menuNo': menu_no,
            'pageIndex': page_index,
            'pageUnit': page_unit,
        }

        try:
            logger.info(f"뉴스 페이지 {page_index} 요청 중...")
            response = self.session.get(self.NEWS_LIST_URL, params=params, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except requests.RequestException as e:
            logger.error(f"페이지 요청 실패: {e}")
            return None

    def parse_news_page(self, html: str) -> list[NewsItem]:
        """
        뉴스/보도자료 페이지에서 게시물 목록을 파싱합니다.

        Args:
            html: HTML 문자열

        Returns:
            NewsItem 리스트
        """
        soup = BeautifulSoup(html, 'html.parser')
        items = []

        # 의사록 관련 게시물 찾기
        links = soup.select('a[href*="view.do"], a[href*="nttId"]')

        for link in links:
            title = link.get_text(strip=True)
            if not title or len(title) < 2:
                continue

            # 의사록 관련 게시물만 필터링
            if '의사록' not in title and '금융통화위원회' not in title:
                continue

            href = link.get('href', '')
            url = self._make_full_url(href)

            # 부모 요소에서 날짜 찾기
            parent = link.find_parent(['li', 'tr', 'div'])
            date = ''
            if parent:
                text = parent.get_text()
                date_match = re.search(r'\d{4}[.\-/]\d{2}[.\-/]\d{2}', text)
                if date_match:
                    date = date_match.group()

            items.append(NewsItem(
                title=title,
                date=date,
                url=url
            ))

        return items

    def get_news_list(self, menu_no: str = "200789", pages: int = 1, page_unit: int = 10) -> list[NewsItem]:
        """
        뉴스/보도자료 목록을 수집합니다.

        Args:
            menu_no: 메뉴 번호
            pages: 수집할 페이지 수
            page_unit: 페이지당 게시물 수

        Returns:
            NewsItem 리스트
        """
        all_items = []

        for page in range(1, pages + 1):
            html = self.fetch_news_page(menu_no=menu_no, page_index=page, page_unit=page_unit)
            if html:
                items = self.parse_news_page(html)
                all_items.extend(items)
                logger.info(f"뉴스 페이지 {page}: {len(items)}개 항목 수집")

            if page < pages:
                time.sleep(1.0)

        return all_items


def save_to_json(items: list, filename: str):
    """결과를 JSON 파일로 저장합니다."""
    output_dir = Path(__file__).parent.parent.parent / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename

    data = [asdict(item) for item in items]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"결과 저장 완료: {output_path}")
    return output_path


def main():
    """메인 실행 함수"""
    crawler = BOKMinutesCrawler()

    logger.info("한국은행 금융통화위원회 의사록 크롤러 시작")

    # 2025년, 2026년 의사록 수집
    target_years = [2025, 2026]
    
    all_items = []

    for year in target_years:
        logger.info(f"{year}년 통화정책방향 결정회의 의사록 수집")
        items = crawler.get_minutes_by_year(year)
        logger.info(f"{year}년: {len(items)}개 회의 발견")
        
        if items:
            output_path = save_to_json(items, f"minutes_{year}.json")
            print(f"{year}년 결과 저장: {output_path}")
            all_items.extend(items)

    # 간단한 요약 출력
    print("\n수집 현황 요약:")
    for i, item in enumerate(all_items, 1):
        has_minutes = bool(item.minutes_pdf_url or item.minutes_hwp_url or item.minutes_url)
        status = "[O]" if has_minutes else "[ ]"
        print(f"{status} {item.meeting_date} (의사록: {'있음' if has_minutes else '없음'})")

    return all_items


if __name__ == "__main__":
    main()
