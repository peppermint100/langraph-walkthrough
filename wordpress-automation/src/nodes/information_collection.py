from typing import Dict, Any
from datetime import datetime
from loguru import logger

from ..models.state import BlogState, WorkflowStatus
from ..models.content_models import CollectedContent, ContentType
from ..utils.perplexity_client import get_perplexity_client


async def information_collection_node(state: BlogState) -> Dict[str, Any]:
    """
    정보 수집 노드 - Perplexity API를 사용하여 주제 관련 정보 수집

    Args:
        state: 현재 워크플로우 상태

    Returns:
        업데이트된 상태 딕셔너리
    """

    logger.info(f"정보 수집 시작: {state.topic}")

    try:
        # 상태 업데이트
        state.set_status(WorkflowStatus.COLLECTING, "Perplexity API를 통한 정보 수집")
        state.update_progress("정보 수집 중", 10)

        if not state.started_at:
            state.started_at = datetime.now().isoformat()

        # Perplexity 클라이언트 가져오기
        perplexity_client = get_perplexity_client()

        # 검색 쿼리 생성
        state.add_log("다각도 검색 쿼리 생성")
        search_queries = perplexity_client.create_search_queries(state.topic)
        state.update_progress("검색 쿼리 생성 완료", 20)

        # 다중 검색 실행
        state.add_log(f"{len(search_queries)}개의 검색 쿼리 동시 실행")
        search_results = await perplexity_client.multi_search(search_queries)
        state.update_progress("검색 결과 수집 완료", 60)

        # 수집된 콘텐츠 정리
        collected_content = CollectedContent(topic=state.topic)

        for content_type, sources in search_results.items():
            for source in sources:
                collected_content.add_source(source)

            state.add_log(f"{content_type.value}: {len(sources)}개 소스 수집")

        state.update_progress("콘텐츠 정리 완료", 80)

        # 수집 결과 검증
        if collected_content.total_sources == 0:
            error_msg = f"'{state.topic}' 주제에 대한 정보를 찾을 수 없습니다"
            state.add_error(error_msg)
            logger.error(error_msg)
            return {"collected_content": None, "status": WorkflowStatus.FAILED}

        # 품질 검증
        high_quality_sources = [
            source for source in collected_content.get_all_sources()
            if source.credibility_score >= 0.6
        ]

        if len(high_quality_sources) < 3:
            logger.warning(f"고품질 소스가 부족합니다: {len(high_quality_sources)}개")
            state.add_log(f"경고: 고품질 소스 {len(high_quality_sources)}개만 발견")

        # 상태 업데이트
        state.collected_content = collected_content
        state.node_outputs["information_collection"] = {
            "total_sources": collected_content.total_sources,
            "basic_concepts": len(collected_content.basic_concepts),
            "latest_trends": len(collected_content.latest_trends),
            "practical_cases": len(collected_content.practical_cases),
            "expert_opinions": len(collected_content.expert_opinions),
            "high_quality_sources": len(high_quality_sources),
            "collection_timestamp": collected_content.collection_timestamp
        }

        state.update_progress("정보 수집 완료", 100)
        state.add_log(f"총 {collected_content.total_sources}개 소스 수집 완료")

        logger.info(f"정보 수집 완료: {collected_content.total_sources}개 소스")

        return {
            "collected_content": collected_content,
            "status": WorkflowStatus.WRITING,
            "current_step": "블로그 글 작성 준비",
            "progress_percentage": 100,
            "node_outputs": state.node_outputs
        }

    except Exception as e:
        error_msg = f"정보 수집 중 오류 발생: {str(e)}"
        logger.error(error_msg)
        state.add_error(error_msg)

        return {
            "status": WorkflowStatus.FAILED,
            "errors": state.errors
        }


def validate_collected_content(collected_content: CollectedContent) -> Dict[str, Any]:
    """
    수집된 콘텐츠의 품질 및 완성도 검증

    Args:
        collected_content: 수집된 콘텐츠

    Returns:
        검증 결과
    """

    validation_result = {
        "is_valid": True,
        "issues": [],
        "recommendations": [],
        "quality_score": 0.0
    }

    # 최소 소스 수 검증
    if collected_content.total_sources < 5:
        validation_result["issues"].append(f"소스 수가 부족합니다: {collected_content.total_sources}개")
        validation_result["recommendations"].append("더 다양한 키워드로 추가 검색 필요")

    # 콘텐츠 타입별 균형 검증
    type_counts = {
        "basic_concepts": len(collected_content.basic_concepts),
        "latest_trends": len(collected_content.latest_trends),
        "practical_cases": len(collected_content.practical_cases),
        "expert_opinions": len(collected_content.expert_opinions)
    }

    empty_types = [k for k, v in type_counts.items() if v == 0]
    if empty_types:
        validation_result["issues"].append(f"누락된 콘텐츠 타입: {', '.join(empty_types)}")
        validation_result["recommendations"].append("누락된 타입에 대한 추가 검색 필요")

    # 신뢰도 점수 검증
    all_sources = collected_content.get_all_sources()
    avg_credibility = sum(source.credibility_score for source in all_sources) / len(all_sources) if all_sources else 0

    if avg_credibility < 0.5:
        validation_result["issues"].append(f"평균 신뢰도가 낮습니다: {avg_credibility:.2f}")
        validation_result["recommendations"].append("더 신뢰할 수 있는 소스에서 정보 수집 필요")

    # 전체 품질 점수 계산
    quality_factors = {
        "source_count": min(1.0, collected_content.total_sources / 10),  # 10개 이상이면 만점
        "type_balance": 1.0 - (len(empty_types) / 4),  # 타입별 균형
        "credibility": avg_credibility,  # 평균 신뢰도
        "content_richness": min(1.0, sum(len(source.summary) for source in all_sources) / 1000)  # 내용 풍부함
    }

    validation_result["quality_score"] = sum(quality_factors.values()) / len(quality_factors)

    # 전체 유효성 판단
    if len(validation_result["issues"]) > 2 or validation_result["quality_score"] < 0.4:
        validation_result["is_valid"] = False

    return validation_result