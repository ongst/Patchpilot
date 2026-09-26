from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    language: str
    issue: str
    files: dict[str, str]
    hidden_tests: dict[str, str]
    test_command: str


PYPROJECT = """[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "patchpilot-eval"
version = "0.0.1"
requires-python = ">=3.10"
"""


def py_task(task_id: str, issue: str, module: str, hidden_test: str) -> EvalTask:
    return EvalTask(
        task_id=task_id,
        language="python",
        issue=issue,
        files={
            "pyproject.toml": PYPROJECT,
            "src/app.py": module,
            "tests/test_smoke.py": "def test_import():\n    import src.app\n",
        },
        hidden_tests={"tests/test_hidden.py": hidden_test},
        test_command="python -m pytest -q",
    )


def js_task(task_id: str, issue: str, module: str, hidden_test: str) -> EvalTask:
    package = """{
  "name": "patchpilot-eval",
  "version": "0.0.1",
  "type": "module",
  "scripts": {"test": "node --test"}
}
"""
    lock = """{
  "name": "patchpilot-eval",
  "version": "0.0.1",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {"": {"name": "patchpilot-eval", "version": "0.0.1"}}
}
"""
    return EvalTask(
        task_id=task_id,
        language="javascript",
        issue=issue,
        files={"package.json": package, "package-lock.json": lock, "src/app.js": module},
        hidden_tests={"test/hidden.test.js": hidden_test},
        test_command="npm test",
    )


TASKS = [
    py_task(
        "py-clamp",
        "clamp(value, low, high) returns the high bound for values below low; correct both boundaries.",
        "def clamp(value, low, high):\n    return max(high, min(low, value))\n",
        "from src.app import clamp\n\ndef test_bounds():\n    assert clamp(-2, 0, 10) == 0\n    assert clamp(12, 0, 10) == 10\n    assert clamp(4, 0, 10) == 4\n",
    ),
    py_task(
        "py-average-empty",
        "average should return 0.0 for an empty iterable instead of raising ZeroDivisionError.",
        "def average(values):\n    values = list(values)\n    return sum(values) / len(values)\n",
        "from src.app import average\n\ndef test_average():\n    assert average([]) == 0.0\n    assert average([2, 4]) == 3.0\n",
    ),
    py_task(
        "py-dedupe-order",
        "unique currently sorts its result. Preserve the original first-seen order.",
        "def unique(values):\n    return sorted(set(values))\n",
        "from src.app import unique\n\ndef test_order():\n    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]\n",
    ),
    py_task(
        "py-parse-bool",
        "parse_bool should accept case-insensitive true/false, yes/no and 1/0 and reject unknown strings.",
        "def parse_bool(value):\n    return value == 'true'\n",
        "import pytest\nfrom src.app import parse_bool\n\ndef test_values():\n    assert parse_bool('YES') is True\n    assert parse_bool('0') is False\n    with pytest.raises(ValueError): parse_bool('maybe')\n",
    ),
    py_task(
        "py-retry-count",
        "run_with_retries performs one extra retry. attempts means total calls, including the first call.",
        "def run_with_retries(fn, attempts):\n    for _ in range(attempts + 1):\n        try:\n            return fn()\n        except RuntimeError:\n            pass\n    raise RuntimeError('failed')\n",
        "import pytest\nfrom src.app import run_with_retries\n\ndef test_attempts():\n    calls=[]\n    def fail(): calls.append(1); raise RuntimeError()\n    with pytest.raises(RuntimeError): run_with_retries(fail, 2)\n    assert len(calls) == 2\n",
    ),
    py_task(
        "py-slugify",
        "slugify leaves repeated separators and surrounding dashes. Normalize whitespace and dashes.",
        "import re\n\ndef slugify(text):\n    return re.sub(r'\\s', '-', text.lower())\n",
        "from src.app import slugify\n\ndef test_slug():\n    assert slugify('  Hello   World-- ') == 'hello-world'\n",
    ),
    js_task(
        "js-chunk",
        "chunk drops the final partial chunk. It must include every input element.",
        "export function chunk(items, size) { const out=[]; for(let i=0;i+size<=items.length;i+=size) out.push(items.slice(i,i+size)); return out }\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {chunk} from '../src/app.js'; test('partial',()=>assert.deepEqual(chunk([1,2,3],2),[[1,2],[3]]));\n",
    ),
    js_task(
        "js-capitalize",
        "capitalize throws for empty strings and lowercases the remaining characters unexpectedly.",
        "export const capitalize = value => value[0].toUpperCase() + value.slice(1).toLowerCase();\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {capitalize} from '../src/app.js'; test('values',()=>{assert.equal(capitalize(''),'');assert.equal(capitalize('hELLo'),'HELLo')});\n",
    ),
    js_task(
        "js-palindrome",
        "isPalindrome should ignore punctuation, spaces and letter case.",
        "export function isPalindrome(value) { return value === value.split('').reverse().join('') }\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {isPalindrome} from '../src/app.js'; test('phrase',()=>assert.equal(isPalindrome('A man, a plan, a canal: Panama'),true));\n",
    ),
    js_task(
        "js-sum-prices",
        "sumPrices concatenates numeric strings. It should return a numeric total.",
        "export function sumPrices(items) { return items.reduce((sum,item)=>sum+item.price, 0) }\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {sumPrices} from '../src/app.js'; test('numeric strings',()=>assert.equal(sumPrices([{price:'2.5'},{price:3}]),5.5));\n",
    ),
    js_task(
        "js-unique-by",
        "uniqueBy keeps the last object for each key; the API contract requires keeping the first.",
        "export function uniqueBy(items,key) { return [...new Map(items.map(item=>[item[key],item])).values()] }\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {uniqueBy} from '../src/app.js'; test('first',()=>assert.deepEqual(uniqueBy([{id:1,v:'a'},{id:1,v:'b'}],'id'),[{id:1,v:'a'}]));\n",
    ),
    js_task(
        "js-format-duration",
        "formatDuration produces 1:5 for 65 seconds. Seconds must always use two digits.",
        "export function formatDuration(total) { return `${Math.floor(total/60)}:${total%60}` }\n",
        "import test from 'node:test'; import assert from 'node:assert/strict'; import {formatDuration} from '../src/app.js'; test('padding',()=>{assert.equal(formatDuration(65),'1:05');assert.equal(formatDuration(9),'0:09')});\n",
    ),
]
