import json

with open('benchmarks/tasks.v2.json', encoding='utf-8') as f:
    d = json.load(f)

new_tasks = [
    {
        'id': 'v2-fix-off-by-one',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'list_utils.py 中的 get_last 函数有 off-by-one 错误，修复它使测试通过。',
        'fixture': {
            'list_utils.py': 'def get_last(lst):\n    return lst[len(lst)]\n',
            'test_list_utils.py': 'from list_utils import get_last\n\n\ndef test_get_last():\n    assert get_last([1, 2, 3]) == 3\n    assert get_last(["a", "b"]) == "b"\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_list_utils.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-fix-empty-list',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': '处理 empty_list.py 中的空列表情况，避免 IndexError。测试预期空列表返回 None。',
        'fixture': {
            'empty_list.py': 'def first_item(lst):\n    return lst[0]\n',
            'test_empty_list.py': 'from empty_list import first_item\n\n\ndef test_empty():\n    assert first_item([]) is None\n    assert first_item([1, 2]) == 1\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_empty_list.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-fix-division',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'calc.py 中的 safe_divide 函数未处理除零情况，修复它返回 None 而非抛出异常。',
        'fixture': {
            'calc.py': 'def safe_divide(a, b):\n    return a / b\n',
            'test_calc.py': 'from calc import safe_divide\n\n\ndef test_divide():\n    assert safe_divide(10, 2) == 5\n    assert safe_divide(10, 0) is None\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_calc.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-multi-crud',
        'category': 'multi-file',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 12,
        'prompt': '实现简单的 CRUD 模块：创建 models.py (User 类)、storage.py (内存存储)、api.py (增删改查函数)。',
        'fixture': {
            'models.py': '',
            'storage.py': '',
            'api.py': '',
            'test_crud.py': 'from models import User\nfrom storage import MemoryStorage\nfrom api import create_user, get_user, update_user, delete_user\n\n\ndef test_crud():\n    storage = MemoryStorage()\n    u = create_user(storage, "alice", "alice@example.com")\n    assert u.id == 1\n    assert u.name == "alice"\n    assert get_user(storage, 1).email == "alice@example.com"\n    update_user(storage, 1, email="alice2@example.com")\n    assert get_user(storage, 1).email == "alice2@example.com"\n    delete_user(storage, 1)\n    assert get_user(storage, 1) is None\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_crud.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-multi-config-toml',
        'category': 'multi-file',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 10,
        'prompt': '创建配置系统：config.py (读取 TOML)、settings.toml (配置文件)、cli.py (打印配置)。',
        'fixture': {
            'config.py': '',
            'settings.toml': '[app]\nname = "myapp"\nport = 8080\n',
            'cli.py': '',
            'test_config.py': 'from config import load_config\n\ndef test_load():\n    cfg = load_config("settings.toml")\n    assert cfg["app"]["name"] == "myapp"\n    assert cfg["app"]["port"] == 8080\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m pytest -q test_config.py',
            'expect_exit': 0
        }
    },
    {
        'id': 'v2-write-readme-badge',
        'category': 'write',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 5,
        'prompt': '在 README.md 中添加一行徽章：[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]。保持原有内容。',
        'fixture': {
            'README.md': '# My Project\n\nA simple project.\n'
        },
        'grader': {
            'type': 'file_contract',
            'files': [
                {'path': 'README.md', 'contains': '# My Project'},
                {'path': 'README.md', 'contains': 'tests-passing-brightgreen'}
            ]
        }
    },
    {
        'id': 'v2-write-gitignore',
        'category': 'write',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 5,
        'prompt': '创建 .gitignore 文件，包含 Python、Node.js、IDE 常见忽略规则。',
        'fixture': {
            'README.md': '# Project\n'
        },
        'grader': {
            'type': 'file_contract',
            'files': [
                {'path': '.gitignore', 'contains': '__pycache__'},
                {'path': '.gitignore', 'contains': 'node_modules'},
                {'path': '.gitignore', 'contains': '.venv'}
            ]
        }
    },
    {
        'id': 'v2-fix-type-hint',
        'category': 'test-fix',
        'suite_version': 'v2-1',
        'allow_changes': True,
        'max_minutes': 8,
        'prompt': 'typed_func.py 中的函数类型注解有误，修复它使 mypy 检查通过。',
        'fixture': {
            'typed_func.py': 'def add(a: int, b: int) -> str:\n    return a + b\n',
            'test_typed.py': 'from typed_func import add\n\ndef test_add():\n    assert add(1, 2) == 3\n'
        },
        'grader': {
            'type': 'command_contract',
            'command': '{python} -m mypy typed_func.py --ignore-missing-imports && {python} -m pytest -q test_typed.py',
            'expect_exit': 0
        }
    }
]

d.extend(new_tasks)

with open('benchmarks/tasks.v2.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('Total tasks:', len(d))
for t in d[-9:]:
    print(f'  {t["id"]}: {t["category"]}')