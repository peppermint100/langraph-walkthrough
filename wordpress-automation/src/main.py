import asyncio
import os
from datetime import datetime
from typing import Dict, Any
from loguru import logger
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.state import BlogState, WorkflowStatus
from src.models.content_models import ContentType
from src.nodes.information_collection import information_collection_node
from src.nodes.blog_writing import blog_writing_node


# 환경 변수 로드
load_dotenv()


def create_workflow() -> StateGraph:
    """
    LangGraph 워크플로우 생성

    Returns:
        구성된 StateGraph 객체
    """

    # StateGraph 생성
    workflow = StateGraph(BlogState)

    # 노드 추가
    workflow.add_node("information_collection", information_collection_node)
    workflow.add_node("blog_writing", blog_writing_node)

    # 시작점 설정
    workflow.set_entry_point("information_collection")

    # 엣지 추가 (노드 간 연결)
    workflow.add_edge("information_collection", "blog_writing")
    workflow.add_edge("blog_writing", END)

    # 조건부 엣지 추가 (상태에 따른 분기)
    def should_continue_to_writing(state: BlogState) -> str:
        """정보 수집 후 다음 단계 결정"""
        if state.status == WorkflowStatus.FAILED:
            return END
        elif state.collected_content and state.collected_content.total_sources > 0:
            return "blog_writing"
        else:
            return END

    workflow.add_conditional_edges(
        "information_collection",
        should_continue_to_writing,
        {
            "blog_writing": "blog_writing",
            END: END
        }
    )

    def should_complete_workflow(state: BlogState) -> str:
        """블로그 작성 후 워크플로우 완료 여부 결정"""
        if state.status == WorkflowStatus.FAILED:
            return END
        elif state.generated_article:
            return END
        else:
            return END

    workflow.add_conditional_edges(
        "blog_writing",
        should_complete_workflow,
        {END: END}
    )

    return workflow


async def run_blog_automation(
    topic: str,
    target_audience: str = "일반",
    tone: str = "친근하고 정보성",
    save_result: bool = True,
    output_dir: str = "./output"
) -> Dict[str, Any]:
    """
    블로그 자동화 파이프라인 실행

    Args:
        topic: 블로그 주제
        target_audience: 타겟 독자층
        tone: 글의 톤앤매너
        save_result: 결과 파일 저장 여부
        output_dir: 출력 디렉토리

    Returns:
        실행 결과
    """

    logger.info(f"블로그 자동화 시작: '{topic}'")

    try:
        # 초기 상태 생성
        initial_state = BlogState(
            topic=topic,
            target_audience=target_audience,
            tone=tone,
            started_at=datetime.now().isoformat()
        )

        # 워크플로우 생성 및 컴파일
        workflow = create_workflow()
        checkpointer = MemorySaver()
        app = workflow.compile(checkpointer=checkpointer)

        # 워크플로우 실행
        config = {"configurable": {"thread_id": f"blog_{datetime.now().strftime('%Y%m%d_%H%M%S')}"}}

        logger.info("LangGraph 워크플로우 실행 시작")
        final_state = None

        async for output in app.astream(initial_state, config=config):
            for node_name, node_output in output.items():
                logger.info(f"노드 '{node_name}' 실행 완료")
                if isinstance(node_output, dict) and "status" in node_output:
                    logger.info(f"상태: {node_output.get('status')}")

                # 최종 상태 업데이트
                if isinstance(node_output, BlogState):
                    final_state = node_output
                elif isinstance(node_output, dict):
                    # 딕셔너리 출력을 상태에 반영
                    if final_state is None:
                        final_state = initial_state
                    for key, value in node_output.items():
                        if hasattr(final_state, key):
                            setattr(final_state, key, value)

        # 최종 상태가 없으면 초기 상태 사용
        if final_state is None:
            final_state = initial_state
            final_state.set_status(WorkflowStatus.FAILED, "워크플로우 실행 실패")

        # 완료 시간 설정
        if final_state.status != WorkflowStatus.FAILED:
            final_state.completed_at = datetime.now().isoformat()
            final_state.set_status(WorkflowStatus.COMPLETED, "블로그 자동화 완료")

        logger.info(f"워크플로우 완료: {final_state.status}")

        # 결과 저장
        result_data = final_state.get_summary()
        if save_result and final_state.generated_article:
            save_path = await save_blog_result(final_state, output_dir)
            result_data["saved_file"] = save_path

        return {
            "success": final_state.status == WorkflowStatus.COMPLETED,
            "final_state": final_state,
            "summary": result_data
        }

    except Exception as e:
        error_msg = f"블로그 자동화 실행 중 오류: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "final_state": None
        }


async def save_blog_result(state: BlogState, output_dir: str) -> str:
    """
    블로그 자동화 결과를 파일로 저장

    Args:
        state: 최종 상태
        output_dir: 출력 디렉토리

    Returns:
        저장된 파일 경로
    """

    os.makedirs(output_dir, exist_ok=True)

    # 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c for c in state.topic if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_topic = safe_topic.replace(' ', '_')[:50]
    filename = f"blog_{safe_topic}_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    # 마크다운 내용 생성
    markdown_content = f"""# {state.generated_article.title}

**생성 일시**: {state.completed_at}
**주제**: {state.topic}
**타겟 독자**: {state.target_audience}
**톤앤매너**: {state.tone}
**예상 읽기 시간**: {state.generated_article.estimated_read_time}분
**단어 수**: {state.generated_article.word_count}자

---

## 메타데이터

- **카테고리**: {state.generated_article.category}
- **태그**: {', '.join(state.generated_article.meta_tags)}
- **키워드**: {', '.join(state.generated_article.keywords)}

---

## 본문

{state.generated_article.content}

---

## 생성 정보

### 수집된 소스
- **총 소스 수**: {state.collected_content.total_sources}
- **기본 개념**: {len(state.collected_content.basic_concepts)}개
- **최신 트렌드**: {len(state.collected_content.latest_trends)}개
- **전문가 의견**: {len(state.collected_content.expert_opinions)}개

### 처리 로그
"""

    # 로그 추가
    for log in state.logs:
        markdown_content += f"- {log}\n"

    # 에러가 있으면 추가
    if state.errors:
        markdown_content += "\n### 발생한 오류\n"
        for error in state.errors:
            markdown_content += f"- {error}\n"

    # 파일 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    logger.info(f"블로그 결과 저장 완료: {filepath}")
    return filepath


def print_workflow_summary(result: Dict[str, Any]):
    """워크플로우 실행 결과 요약 출력"""

    print("\n" + "="*60)
    print("🤖 WordPress 블로그 자동화 결과")
    print("="*60)

    if result["success"]:
        state = result["final_state"]
        summary = result["summary"]

        print(f"✅ 상태: 성공")
        print(f"📝 주제: {summary['topic']}")
        print(f"📊 진행률: {summary['progress']}")
        print(f"📄 생성된 글: '{state.generated_article.title}'")
        print(f"📝 단어 수: {summary['word_count']}자")
        print(f"⏱️  예상 읽기 시간: {state.generated_article.estimated_read_time}분")
        print(f"🔍 수집된 소스: {summary['sources_collected']}개")

        if "saved_file" in summary:
            print(f"💾 저장된 파일: {summary['saved_file']}")

        print(f"🕐 시작: {summary['started_at']}")
        print(f"🕐 완료: {summary['completed_at']}")

    else:
        print(f"❌ 상태: 실패")
        print(f"🚨 오류: {result.get('error', '알 수 없는 오류')}")

    print("="*60 + "\n")


async def main():
    """메인 실행 함수"""

    # 기본 설정
    logger.add("logs/blog_automation_{time}.log", rotation="1 day")

    # 예제 실행
    topic = "마포구 한의원"

    print(f"🚀 블로그 자동화 시작: '{topic}'")
    print("Processing... (몇 분 소요될 수 있습니다)\n")

    result = await run_blog_automation(
        topic=topic,
        target_audience="일반인",
        tone="친근하고 이해하기 쉬운",
        save_result=True,
        output_dir="./output"
    )

    print_workflow_summary(result)


if __name__ == "__main__":
    asyncio.run(main())