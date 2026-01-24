"""
한국은행 금융통화위원회 의사록 PDF 다운로드 및 텍스트 추출

수집된 의사록 목록에서 PDF 파일을 다운로드하고,
pdfplumber를 사용하여 텍스트를 추출합니다.
"""

import requests
import pdfplumber
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
TEXT_DIR = DATA_DIR / "texts"
RAW_DIR = DATA_DIR / "raw"


@dataclass
class DownloadResult:
    """다운로드 결과"""
    success: bool
    file_path: Optional[Path] = None
    error: Optional[str] = None


class PDFDownloader:
    """PDF 다운로드 및 텍스트 추출기"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://www.bok.or.kr/'
        })

        # 디렉토리 생성
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        TEXT_DIR.mkdir(parents=True, exist_ok=True)

    def download_pdf(self, url: str, filename: str) -> DownloadResult:
        """
        PDF 파일을 다운로드합니다.

        Args:
            url: PDF 다운로드 URL
            filename: 저장할 파일명 (확장자 제외)

        Returns:
            DownloadResult
        """
        if not url:
            return DownloadResult(success=False, error="URL이 비어있습니다")

        file_path = PDF_DIR / f"{filename}.pdf"

        # 이미 다운로드된 파일이 있으면 스킵
        if file_path.exists() and file_path.stat().st_size > 0:
            logger.info(f"이미 존재: {filename}.pdf")
            return DownloadResult(success=True, file_path=file_path)

        try:
            logger.info(f"다운로드 중: {filename}.pdf")
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()

            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and 'octet-stream' not in content_type.lower():
                logger.warning(f"예상치 못한 Content-Type: {content_type}")

            # 파일 저장
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 파일 크기 확인
            if file_path.stat().st_size < 1000:
                file_path.unlink()
                return DownloadResult(success=False, error="파일이 너무 작음 (손상된 파일)")

            logger.info(f"다운로드 완료: {filename}.pdf ({file_path.stat().st_size:,} bytes)")
            return DownloadResult(success=True, file_path=file_path)

        except requests.RequestException as e:
            logger.error(f"다운로드 실패 ({filename}): {e}")
            return DownloadResult(success=False, error=str(e))

    def extract_text(self, pdf_path: Path, output_filename: str) -> Optional[Path]:
        """
        PDF에서 텍스트를 추출합니다.

        Args:
            pdf_path: PDF 파일 경로
            output_filename: 출력 파일명 (확장자 제외)

        Returns:
            텍스트 파일 경로 또는 None
        """
        if not pdf_path or not pdf_path.exists():
            logger.error(f"PDF 파일이 존재하지 않음: {pdf_path}")
            return None

        text_path = TEXT_DIR / f"{output_filename}.txt"

        # 이미 추출된 파일이 있으면 스킵
        if text_path.exists() and text_path.stat().st_size > 0:
            logger.info(f"이미 추출됨: {output_filename}.txt")
            return text_path

        try:
            logger.info(f"텍스트 추출 중: {pdf_path.name}")

            all_text = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text:
                        all_text.append(f"--- 페이지 {i} ---\n{text}")

            if not all_text:
                logger.warning(f"텍스트를 추출할 수 없음: {pdf_path.name}")
                return None

            # 텍스트 저장
            full_text = "\n\n".join(all_text)
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(full_text)

            logger.info(f"텍스트 추출 완료: {output_filename}.txt ({len(full_text):,} chars)")
            return text_path

        except Exception as e:
            logger.error(f"텍스트 추출 실패 ({pdf_path.name}): {e}")
            return None

    def process_minutes_file(self, json_path: Path, delay: float = 1.0) -> dict:
        """
        의사록 JSON 파일을 처리하여 PDF 다운로드 및 텍스트 추출을 수행합니다.

        Args:
            json_path: 의사록 JSON 파일 경로
            delay: 요청 간 대기 시간(초)

        Returns:
            처리 결과 통계
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            minutes_list = json.load(f)

        stats = {
            'total': len(minutes_list),
            'downloaded': 0,
            'extracted': 0,
            'skipped': 0,
            'failed': 0
        }

        for item in minutes_list:
            meeting_date = item.get('meeting_date', 'unknown')
            year = item.get('year', 'unknown')

            # 파일명 생성 (예: minutes_2024_01_11)
            date_str = meeting_date.replace('.', '_')
            filename = f"minutes_{date_str}"

            # PDF URL 선택 (PDF 우선, 없으면 HWP 건너뛰기)
            pdf_url = item.get('minutes_pdf_url')
            if not pdf_url:
                logger.info(f"PDF URL 없음: {meeting_date}")
                stats['skipped'] += 1
                continue

            # PDF 다운로드
            result = self.download_pdf(pdf_url, filename)
            if result.success:
                stats['downloaded'] += 1

                # 텍스트 추출
                text_path = self.extract_text(result.file_path, filename)
                if text_path:
                    stats['extracted'] += 1
            else:
                stats['failed'] += 1

            time.sleep(delay)

        return stats

    def process_all_years(self, years: list[int] = None, delay: float = 1.0) -> dict:
        """
        여러 연도의 의사록을 처리합니다.

        Args:
            years: 처리할 연도 목록
            delay: 요청 간 대기 시간(초)

        Returns:
            전체 처리 결과 통계
        """
        if years is None:
            # RAW_DIR에서 사용 가능한 연도 자동 감지
            years = []
            for f in RAW_DIR.glob("minutes_*.json"):
                try:
                    year = int(f.stem.split('_')[1])
                    years.append(year)
                except (IndexError, ValueError):
                    continue
            years.sort()

        total_stats = {
            'total': 0,
            'downloaded': 0,
            'extracted': 0,
            'skipped': 0,
            'failed': 0
        }

        for year in years:
            json_path = RAW_DIR / f"minutes_{year}.json"
            if not json_path.exists():
                logger.warning(f"파일 없음: {json_path}")
                continue

            logger.info(f"\n{'='*50}")
            logger.info(f"{year}년 의사록 처리 시작")
            logger.info('='*50)

            stats = self.process_minutes_file(json_path, delay=delay)

            # 통계 합산
            for key in total_stats:
                total_stats[key] += stats[key]

            logger.info(f"{year}년 완료: 다운로드 {stats['downloaded']}, 추출 {stats['extracted']}, 스킵 {stats['skipped']}, 실패 {stats['failed']}")

        return total_stats


def main():
    """메인 실행 함수"""
    downloader = PDFDownloader()

    print("=" * 60)
    print("한국은행 금융통화위원회 의사록 PDF 다운로드 및 텍스트 추출")
    print("=" * 60)

    # 모든 연도 처리
    stats = downloader.process_all_years(delay=0.5)

    print("\n" + "=" * 60)
    print("처리 완료")
    print("=" * 60)
    print(f"총 회의: {stats['total']}개")
    print(f"다운로드: {stats['downloaded']}개")
    print(f"텍스트 추출: {stats['extracted']}개")
    print(f"스킵 (PDF 없음): {stats['skipped']}개")
    print(f"실패: {stats['failed']}개")
    print(f"\nPDF 저장 위치: {PDF_DIR}")
    print(f"텍스트 저장 위치: {TEXT_DIR}")


if __name__ == "__main__":
    main()
