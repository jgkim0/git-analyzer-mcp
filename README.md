# git-analyzer-mcp

로컬 git 저장소를 들여다보는 MCP(Model Context Protocol) 서버입니다. Claude 같은
MCP 호환 클라이언트가 이 서버를 통해 커밋 히스토리 조회, diff 확인, blame,
커밋 메시지 검색, 브랜치 목록, 파일별 변경 이력, working tree 상태를 직접
확인할 수 있게 해줍니다.

모든 도구는 **읽기 전용**입니다 (`git log`, `git diff`, `git blame`, `git status`,
`git branch` 만 실행하고, 저장소 내용을 바꾸는 명령은 실행하지 않습니다).

## 제공하는 도구

| 도구 | 설명 |
|---|---|
| `list_recent_commits` | 최근 커밋 목록 조회 (개수, 브랜치 지정 가능) |
| `get_diff` | 두 ref(커밋/브랜치/태그) 간, 또는 ref와 working tree 간 diff |
| `search_commits` | 커밋 메시지 검색 (브랜치 범위 지정 또는 `--all`) |
| `list_branches` | 로컬/원격 브랜치 목록과 현재 브랜치 |
| `get_file_history` | 특정 파일을 수정한 커밋 목록 |
| `blame_file` | 파일의 줄 단위 blame (각 줄을 마지막으로 수정한 커밋/작성자) |
| `get_status` | 현재 브랜치, staged/modified/untracked 파일 목록 |

## 설치

```bash
cd git-analyzer-mcp
pip install -e .
```

`mcp` 패키지만 의존성으로 필요합니다 (GitPython 등은 사용하지 않고, 시스템에
설치된 `git` 명령을 직접 호출합니다). 로컬 환경에 `git` CLI가 설치되어 있어야
합니다.

## 직접 실행해보기 (개발용)

```bash
python -m git_analyzer_mcp.server
```

MCP 서버는 stdio를 통해 통신하도록 설계되어 있어서, 이 명령만 실행하면 터미널에는
아무 출력도 없이 대기 상태가 됩니다 (정상입니다). 실제 확인은 아래처럼 클라이언트에
연결해서 하거나, `git_ops.py`의 함수들을 파이썬에서 직접 호출해서 테스트하세요.

```python
from git_analyzer_mcp import git_ops

print(git_ops.get_recent_commits("/path/to/some/repo", count=5))
```

## Claude Desktop에 연결하기

Claude Desktop 설정 파일(`claude_desktop_config.json`)의 `mcpServers`에 아래
항목을 추가하세요.

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "git-analyzer": {
      "command": "python",
      "args": ["-m", "git_analyzer_mcp.server"],
      "cwd": "/absolute/path/to/git-analyzer-mcp"
    }
  }
}
```

설정을 저장한 뒤 Claude Desktop을 재시작하면, 대화 중에 "이 프로젝트 최근 커밋
좀 보여줘" 같은 요청을 했을 때 Claude가 이 서버의 도구를 자동으로 호출합니다.
`repo_path`는 도구를 호출할 때마다 절대경로로 넘겨줘야 하므로, 사용하려는
저장소의 경로를 대화에서 알려주면 됩니다.

## 사용 예시 (Claude에게 이렇게 물어보면 됩니다)

- "`/Users/me/projects/myapp` 저장소 최근 커밋 10개 보여줘"
- "main이랑 feature/login 브랜치 diff 좀 보여줘"
- "이 파일(`src/auth.py`) 누가 언제 수정했는지 blame 떠줘"
- "커밋 메시지에 'fix'가 들어간 커밋들 전체 브랜치에서 찾아줘"
- "지금 이 저장소 상태 어때? 커밋 안 된 변경사항 있어?"

## 알아두면 좋은 설계 포인트

- **GitPython 대신 subprocess**: 의존성을 최소화하고, 실제로 어떤 git 명령이
  실행되는지 투명하게 볼 수 있도록 `git` CLI를 직접 호출합니다. 인자는 항상
  리스트로 넘겨 셸 인젝션을 방지합니다 (`shell=True`를 쓰지 않음).
- **에러 처리**: git 명령이 실패하면 예외를 던지는 대신 `{"error": "..."}`
  형태로 반환해서, MCP 호출이 죽지 않고 Claude가 에러 상황을 이해하고 사용자에게
  설명할 수 있게 합니다.
- **출력 크기 제한**: `get_diff`와 `blame_file`은 결과가 너무 크면 잘라내고
  `truncated: true`를 표시합니다. 큰 저장소에서 컨텍스트가 과도하게 커지는 것을
  막기 위한 안전장치입니다.

## 확장 아이디어

- `get_diff`에 `--stat` 옵션을 추가해서 변경된 파일 목록/통계만 빠르게 보기
- 특정 저자(author)로 커밋을 필터링하는 `list_commits_by_author` 도구
- `git log --follow`를 활용해 파일 이름이 바뀌어도 히스토리를 추적하는 기능
- 여러 저장소 경로를 환경변수나 설정 파일로 미리 등록해서 `repo_path`를 매번
  안 넘기고 별칭으로 부를 수 있게 하기
