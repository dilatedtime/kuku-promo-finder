"""Swappable judgment providers. Parsing and source validation belong to the pipeline.

All providers expose complete(messages, purpose='judge') and return the model's
unmodified text in ``content``. No provider silently falls back to another model.
Remote providers require an intentional ``allow_remote: true`` configuration.
Loopback HTTP endpoints and local Transformers inference keep text on this machine.
"""
from __future__ import annotations

import json
import ipaddress
import os
import random
import time
import urllib.error
import urllib.request
import urllib.parse
from typing import Any


class ProviderError(RuntimeError):
    """A clear, actionable model configuration or execution failure."""


def _estimated_tokens(text: str) -> int:
    # This estimate is never labelled as tokenizer or API usage.
    return (len(text) + 3) // 4


def _message_text(messages: list[dict[str, str]]) -> str:
    if not messages or any(not isinstance(x, dict) or not isinstance(x.get('content'), str)
                           or x.get('role') not in {'system', 'user', 'assistant'} for x in messages):
        raise ProviderError('messages must be a nonempty list of role/content dictionaries.')
    return '\n'.join(f"{x['role']}: {x['content']}" for x in messages)


def _result(content: str, *, provider: str, model: str, input_tokens: int,
            output_tokens: int, method: str, started: float, raw: Any = None) -> dict:
    result = {
        'content': content,
        'provider': provider,
        'model': model,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'token_count_method': method,
        'elapsed_seconds': round(time.monotonic() - started, 4),
    }
    if raw is not None:
        result['raw'] = raw
    return result


class MockProvider:
    """Offline plumbing fixture. Its output is not a semantic judgment."""

    def __init__(self, config: dict):
        self.config = config
        self.model = str(config.get('model', 'mock-fixture'))

    def complete(self, messages: list[dict[str, str]], purpose: str = 'judge') -> dict:
        started = time.monotonic()
        text = _message_text(messages)
        fixture = self.config.get('mock_response', {'mock': True, 'judgments': []})
        content = fixture if isinstance(fixture, str) else json.dumps(fixture, ensure_ascii=False)
        return _result(content, provider='mock', model=self.model,
                       input_tokens=_estimated_tokens(text), output_tokens=_estimated_tokens(content),
                       method='estimated_characters_divided_by_4_not_api_usage', started=started,
                       raw={'fixture': True, 'purpose': purpose, 'semantic_judgment': False})


class _HTTPProvider:
    def __init__(self, config: dict):
        self.config = dict(config)
        endpoint = urllib.parse.urlsplit(str(config.get('base_url', '')))
        host = endpoint.hostname or ''
        try:
            self.is_local_endpoint = ipaddress.ip_address(host).is_loopback
        except ValueError:
            self.is_local_endpoint = host.lower() == 'localhost'
        if not self.is_local_endpoint and config.get('allow_remote') is not True:
            raise ProviderError('Remote inference is disabled. Set allow_remote=true in the chosen '
                                'config only when you intentionally want to send screenplay text to that provider.')
        self.model = str(config.get('model', '')).strip()
        if not self.model:
            raise ProviderError('Set a nonempty model name in the provider config.')
        self.timeout = float(config.get('timeout', 90))
        self.retries = int(config.get('retries', 2))
        if self.timeout <= 0 or not 0 <= self.retries <= 5:
            raise ProviderError('timeout must be positive and retries must be between 0 and 5.')

    def _key(self) -> str:
        key_env = self.config.get('api_key_env')
        if not key_env:
            return ''
        key = os.environ.get(str(key_env), '').strip()
        if not key:
            raise ProviderError(f'Missing API credential. Set environment variable {key_env}; '
                                'never put a key in a config or commit it.')
        return key

    def _request(self, url: str, payload: dict, headers: dict) -> dict:
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json', **headers}, method='POST')
        last_error = 'unknown HTTP failure'
        for attempt in range(self.retries + 1):
            retry_after = None
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode('utf-8')
                try:
                    data = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise ProviderError('Provider returned non-JSON HTTP response; no fallback was attempted.') from exc
                if not isinstance(data, dict):
                    raise ProviderError('Provider returned a JSON response that is not an object.')
                return data
            except urllib.error.HTTPError as exc:
                # Do not include request headers, URL query strings, credentials or
                # screenplay-bearing error bodies in exceptions.
                last_error = f'HTTP {exc.code}'
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise ProviderError(f'Provider rejected the request ({last_error}). Check model, '
                                        'credentials and endpoint; no fallback was attempted.') from None
                try:
                    retry_after = min(60.0, max(0.0, float(exc.headers.get('Retry-After', ''))))
                except (TypeError, ValueError):
                    pass
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = type(exc).__name__
            if attempt < self.retries:
                time.sleep(retry_after if retry_after is not None else min(30, 2 ** attempt + random.random()))
        raise ProviderError(f'Provider request failed after {self.retries + 1} attempts ({last_error}). '
                            'Check network, quota and timeout. No paid or alternate model fallback was attempted.')


class OpenAICompatibleProvider(_HTTPProvider):
    """Standard /chat/completions adapter, including local compatible servers."""

    def complete(self, messages: list[dict[str, str]], purpose: str = 'judge') -> dict:
        started = time.monotonic()
        text = _message_text(messages)
        base = str(self.config.get('base_url', '')).rstrip('/')
        if not base.startswith(('http://', 'https://')):
            raise ProviderError('OpenAI-compatible base_url must be an explicit http(s) endpoint ending in /v1 if needed.')
        payload = {'model': self.model, 'messages': messages,
                   'temperature': float(self.config.get('temperature', 0)),
                   'max_tokens': int(self.config.get('max_tokens', 1024))}
        if self.config.get('seed') is not None:
            payload['seed'] = int(self.config['seed'])
        if self.config.get('json_mode', True):
            payload['response_format'] = {'type': 'json_object'}
        key = self._key()
        data = self._request(base + '/chat/completions', payload,
                             {'Authorization': f'Bearer {key}'} if key else {})
        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError('OpenAI-compatible response has no choices[0].message.content.') from exc
        if not isinstance(content, str):
            raise ProviderError('OpenAI-compatible content is not text; check refusal or endpoint schema.')
        usage = data.get('usage', {})
        exact = isinstance(usage.get('prompt_tokens'), int) and isinstance(usage.get('completion_tokens'), int)
        return _result(content, provider='openai_compatible', model=self.model,
                       input_tokens=usage['prompt_tokens'] if exact else _estimated_tokens(text),
                       output_tokens=usage['completion_tokens'] if exact else _estimated_tokens(content),
                       method='api_usage' if exact else 'estimated_characters_divided_by_4_not_api_usage',
                       started=started, raw={**data, '_execution_location': 'loopback' if self.is_local_endpoint else 'remote'})


class GeminiProvider(_HTTPProvider):
    """Gemini generateContent adapter; choose a model eligible for your free quota."""

    def complete(self, messages: list[dict[str, str]], purpose: str = 'judge') -> dict:
        started = time.monotonic()
        text = _message_text(messages)
        system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
        contents = [{'role': 'model' if m['role'] == 'assistant' else 'user',
                     'parts': [{'text': m['content']}]} for m in messages if m['role'] != 'system']
        if not contents:
            raise ProviderError('Gemini needs at least one non-system message.')
        generation = {'temperature': float(self.config.get('temperature', 0)),
                      'maxOutputTokens': int(self.config.get('max_tokens', 1024))}
        if self.config.get('json_mode', True):
            generation['responseMimeType'] = 'application/json'
        if self.config.get('seed') is not None:
            generation['seed'] = int(self.config['seed'])
        payload = {'contents': contents, 'generationConfig': generation}
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}
        base = str(self.config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')).rstrip('/')
        if not base.startswith('https://'):
            raise ProviderError('Gemini base_url must use https://.')
        data = self._request(f'{base}/models/{self.model}:generateContent', payload, {'x-goog-api-key': self._key()})
        try:
            parts = data['candidates'][0]['content']['parts']
            content = ''.join(part.get('text', '') for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError('Gemini returned no text candidate. Check safety blocking and model availability.') from exc
        if not content:
            raise ProviderError('Gemini returned empty text. Check finish reason, safety response and max_tokens.')
        usage = data.get('usageMetadata', {})
        exact = isinstance(usage.get('promptTokenCount'), int) and isinstance(usage.get('candidatesTokenCount'), int)
        return _result(content, provider='gemini', model=self.model,
                       input_tokens=usage['promptTokenCount'] if exact else _estimated_tokens(text),
                       output_tokens=usage['candidatesTokenCount'] if exact else _estimated_tokens(content),
                       method='api_usage' if exact else 'estimated_characters_divided_by_4_not_api_usage',
                       started=started, raw={**data, '_execution_location': 'loopback' if self.is_local_endpoint else 'remote'})


class TransformersProvider:
    """Free, local inference. Model weights download; screenplay text stays local."""

    def __init__(self, config: dict):
        self.config = dict(config)
        self.model = str(config.get('model', 'Qwen/Qwen2.5-1.5B-Instruct'))
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ProviderError('Local inference requires torch>=2.2, transformers>=4.37 and safetensors. '
                                'Install the optional requirements-local.txt dependencies.') from exc
        requested = str(self.config.get('device', 'auto'))
        if requested not in {'auto', 'cpu', 'cuda'}:
            raise ProviderError('Local device must be auto, cpu or cuda.')
        if requested == 'cuda' and not torch.cuda.is_available():
            raise ProviderError('CUDA was requested but torch.cuda.is_available() is false. Choose device=cpu or install CUDA torch.')
        self._device = 'cuda' if requested == 'cuda' or (requested == 'auto' and torch.cuda.is_available()) else 'cpu'
        if self.config.get('threads') is not None:
            threads = int(self.config['threads'])
            if threads < 1:
                raise ProviderError('Local threads must be a positive integer.')
            torch.set_num_threads(threads)
        dtype = torch.float16 if self._device == 'cuda' else torch.float32
        load_args = {'trust_remote_code': False, 'local_files_only': bool(self.config.get('local_files_only', False))}
        if self.config.get('cache_dir'):
            load_args['cache_dir'] = str(self.config['cache_dir'])
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model, **load_args)
            model = AutoModelForCausalLM.from_pretrained(self.model, torch_dtype=dtype,
                                                       low_cpu_mem_usage=False, **load_args)
            model.to(self._device)
            model.eval()
        except Exception as exc:
            raise ProviderError(f'Could not load local model {self.model!r} on {self._device}: '
                                f'{type(exc).__name__}: {exc}. Check model path/download and available memory.') from exc
        self._torch, self._tokenizer, self._model = torch, tokenizer, model

    def complete(self, messages: list[dict[str, str]], purpose: str = 'judge') -> dict:
        started = time.monotonic()
        _message_text(messages)
        self._load()
        torch, tokenizer, model = self._torch, self._tokenizer, self._model
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors='pt').to(self._device)
        input_count = int(inputs['input_ids'].shape[1])
        max_tokens = int(self.config.get('max_tokens', 512))
        if max_tokens < 1:
            raise ProviderError('max_tokens must be positive.')
        context_limit = int(self.config.get('context_limit', getattr(model.config, 'max_position_embeddings', 32768)))
        if input_count + max_tokens > context_limit:
            raise ProviderError(f'Local prompt has {input_count} tokens plus {max_tokens} requested output tokens, '
                                f'exceeding context_limit={context_limit}. Reduce candidate batch size; text was not truncated.')
        temperature = float(self.config.get('temperature', 0))
        if self.config.get('seed') is not None:
            torch.manual_seed(int(self.config['seed']))
            if self._device == 'cuda':
                torch.cuda.manual_seed_all(int(self.config['seed']))
        kwargs = {'max_new_tokens': max_tokens, 'do_sample': temperature > 0,
                  'pad_token_id': tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id}
        if temperature > 0:
            kwargs.update(temperature=temperature, top_p=float(self.config.get('top_p', 0.9)))
        try:
            with torch.inference_mode():
                output = model.generate(**inputs, **kwargs)
        except Exception as exc:
            raise ProviderError(f'Local generation failed on {self._device}: {type(exc).__name__}: {exc}. '
                                'Reduce batch/context/output length or use a smaller local model. No remote fallback was attempted.') from exc
        generated = output[0, input_count:]
        content = tokenizer.decode(generated, skip_special_tokens=True)
        return _result(content, provider='transformers', model=self.model,
                       input_tokens=input_count, output_tokens=int(generated.shape[0]),
                       method='actual_local_tokenizer_counts', started=started,
                       raw={'device': self._device, 'purpose': purpose,
                            'reached_output_limit': int(generated.shape[0]) >= max_tokens,
                            'generation_temperature': temperature})


def create_provider(config: dict):
    """Construct a configured provider. Configuration errors fail before inference."""
    if not isinstance(config, dict):
        raise ProviderError('Provider config must be a JSON object.')
    name = str(config.get('provider', 'mock')).lower()
    providers = {'mock': MockProvider, 'offline': MockProvider,
                 'transformers': TransformersProvider, 'local': TransformersProvider,
                 'openai_compatible': OpenAICompatibleProvider, 'openai-compatible': OpenAICompatibleProvider,
                 'gemini': GeminiProvider}
    if name not in providers:
        raise ProviderError(f'Unknown provider {name!r}. Choose mock, transformers, openai_compatible or gemini.')
    return providers[name](config)
