import json

with open('benchmarks/tasks.v2.json', encoding='utf-8') as f:
    d = json.load(f)

new_tasks = [
    {
        'id': 'v2-fix-unicode',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'unicode_utils.py 中的 normalize 函数未正确处理组合字符，修复它使测试通过。',
        'fixture': {
            'unicode_utils.py': 'import unicodedata\n\ndef normalize(text):\n    return unicodedata.normalize("NFC", text)\n',
            'test_unicode.py': 'from unicode_utils import normalize\n\n\ndef test_combining():\n    # e + combining acute = é\n    assert normalize("e\\u0301") == "é"\n    assert normalize("cafe\\u0301") == "café"\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_unicode.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-fix-async',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 10,
        'prompt': 'async_fetch.py 中的 fetch_all 函数未正确等待所有任务，修复并发问题。',
        'fixture': {
            'async_fetch.py': 'import asyncio\n\nasync def fetch(url):\n    await asyncio.sleep(0.01)\n    return f"data-{url}"\n\nasync def fetch_all(urls):\n    tasks = [fetch(u) for u in urls]\n    return tasks  # Bug: should await\n',
            'test_async.py': 'import asyncio\nfrom async_fetch import fetch_all\n\n\ndef test_fetch_all():\n    urls = ["a", "b", "c"]\n    results = asyncio.run(fetch_all(urls))\n    assert len(results) == 3\n    assert all(r.startswith("data-") for r in results)\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_async.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-fix-json-serialize',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'serializer.py 中的 to_json 未处理 datetime 对象，添加默认序列化器。',
        'fixture': {
            'serializer.py': 'import json\nfrom datetime import datetime\n\ndef to_json(obj):\n    return json.dumps(obj)\n',
            'test_serializer.py': 'from serializer import to_json\nfrom datetime import datetime\n\n\ndef test_datetime():\n    dt = datetime(2024, 1, 1, 12, 0, 0)\n    result = to_json({"time": dt})\n    assert "2024-01-01" in result\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_serializer.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-multi-api-client',
        'category': 'multi-file',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 15,
        'prompt': '实现一个简单的 REST API 客户端：client.py (HTTP 请求)、models.py (响应模型)、endpoints.py (API 端点)。',
        'fixture': {
            'client.py': '',
            'models.py': '',
            'endpoints.py': '',
            'test_client.py': 'from client import ApiClient\nfrom models import User\nfrom endpoints import get_user\n\n\ndef test_client():\n    client = ApiClient("https://api.example.com")\n    # Mock test - just verify structure\n    assert hasattr(client, "get")\n    assert hasattr(client, "post")\n    u = User(id=1, name="test")\n    assert u.id == 1\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_client.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-multi-logger',
        'category': 'multi-file',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 12,
        'prompt': '创建日志模块：logger.py (核心)、handlers.py (文件/控制台处理器)、formatters.py (格式化器)。',
        'fixture': {
            'logger.py': '',
            'handlers.py': '',
            'formatters.py': '',
            'test_logger.py': 'from logger import Logger\nfrom handlers import ConsoleHandler\nfrom formatters import JsonFormatter\n\n\ndef test_logger():\n    logger = Logger("test")\n    logger.add_handler(ConsoleHandler(JsonFormatter()))\n    logger.info("test message")\n    assert logger.name == "test"\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_logger.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-write-pyproject',
        'category': 'write',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 6,
        'prompt': '创建 pyproject.toml，包含 [project] name/version/dependencies、[tool.pytest.ini_options] testpaths。',
        'fixture': {
            'README.md': '# Project\n'
        },
        'grader': {
            'type': 'file_contract',
            'files': [
                {'path': 'pyproject.toml', 'contains': '[project]'},
                {'path': 'pyproject.toml', 'contains': 'name'},
                {'path': 'pyproject.toml', 'contains': 'dependencies'},
                {'path': 'pyproject.toml', 'contains': 'pytest.ini_options'}
            ]
        }
    },
    {
        'id': 'v2-write-dockerfile',
        'category': 'write',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 6,
        'prompt': '创建 Dockerfile：基于 python:3.11-slim，设置工作目录，复制 requirements.txt，安装依赖，复制源码，暴露 8000 端口。',
        'fixture': {
            'requirements.txt': 'fastapi\nuvicorn\n',
            'app.py': 'print("hello")\n'
        },
        'grader': {
            'type': 'file_contract',
            'files': [
                {'path': 'Dockerfile', 'contains': 'FROM python:3.11-slim'},
                {'path': 'Dockerfile', 'contains': 'WORKDIR'},
                {'path': 'Dockerfile', 'contains': 'requirements.txt'},
                {'path': 'Dockerfile', 'contains': 'EXPOSE 8000'}
            ]
        }
    },
    {
        'id': 'v2-write-github-action',
        'category': 'write',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 6,
        'prompt': '创建 .github/workflows/ci.yml：在 push 时运行 pytest，使用 python 3.11，缓存 pip。',
        'fixture': {
            'README.md': '# Project\n'
        },
        'grader': {
            'type': 'file_contract',
            'files': [
                {'path': '.github/workflows/ci.yml', 'contains': 'on: push'},
                {'path': '.github/workflows/ci.yml', 'contains': 'pytest'},
                {'path': '.github/workflows/ci.yml', 'contains': 'python-version'}
            ]
        }
    },
    {
        'id': 'v2-fix-regex',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'validator.py 中的 email 正则不匹配子域名，修复正则使测试通过。',
        'fixture': {
            'validator.py': 'import re\nEMAIL_RE = re.compile(r"^[^@]+@[^@]+\\.[^@]+$")\n\ndef is_valid_email(email):\n    return bool(EMAIL_RE.match(email))\n',
            'test_validator.py': 'from validator import is_valid_email\n\n\ndef test_email():\n    assert is_valid_email("user@example.com")\n    assert is_valid_email("user@mail.example.com")\n    assert is_valid_email("user@sub.mail.example.com")\n    assert not is_valid_email("invalid")\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_validator.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-fix-path-traversal',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'safe_path.py 中的 resolve_path 存在路径遍历漏洞，修复它防止跳出基础目录。',
        'fixture': {
            'safe_path.py': 'from pathlib import Path\n\ndef resolve_path(base, user_path):\n    return Path(base) / user_path\n',
            'test_safe_path.py': 'from safe_path import resolve_path\n\n\ndef test_traversal():\n    base = "/safe"\n    assert str(resolve_path(base, "normal.txt")).startswith("/safe")\n    # This should not escape\n    result = resolve_path(base, "../../../etc/passwd")\n    assert str(result).startswith("/safe")\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_safe_path.py',
            'expect_exit': 0
        }
    }
]

d.extend(new_tasks)

with open('benchmarks/tasks.v2.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('Total tasks:', len(d))
for t in d[-11:]:
    print(f'  {t["id"]}: {t["category"]}')