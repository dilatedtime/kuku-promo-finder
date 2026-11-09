"""Provider contracts tested with synthetic fixtures; no remote API calls."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from promo_finder.providers import ProviderError, create_provider


class Response(io.BytesIO):
    pass


def response(payload):
    return Response(json.dumps(payload).encode('utf-8'))


class ProviderTests(unittest.TestCase):
    messages = [{'role': 'system', 'content': 'Return JSON.'},
                {'role': 'user', 'content': 'Synthetic test only.'}]

    def test_mock_is_explicitly_not_semantic(self):
        result = create_provider({'provider': 'mock'}).complete(self.messages)
        self.assertFalse(result['raw']['semantic_judgment'])
        self.assertEqual(json.loads(result['content']), {'mock': True, 'judgments': []})
        self.assertIn('estimated', result['token_count_method'])

    def test_mock_can_return_deliberately_malformed_fixture(self):
        result = create_provider({'provider': 'mock', 'mock_response': 'not JSON'}).complete(self.messages)
        self.assertEqual(result['content'], 'not JSON')

    def test_unknown_provider_fails(self):
        with self.assertRaisesRegex(ProviderError, 'Unknown provider'):
            create_provider({'provider': 'misspelled'})

    def test_bad_messages_fail(self):
        with self.assertRaisesRegex(ProviderError, 'role/content'):
            create_provider({'provider': 'mock'}).complete([{'role': 'user'}])

    def test_remote_requires_intentional_config(self):
        with self.assertRaisesRegex(ProviderError, 'allow_remote=true'):
            create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                             'base_url': 'https://example.invalid/v1'})

    def test_loopback_needs_no_remote_flag(self):
        for endpoint in ('http://127.0.0.1:8765/v1', 'http://localhost:8765/v1',
                         'http://[::1]:8765/v1'):
            provider = create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                                        'base_url': endpoint, 'allow_remote': False})
            self.assertTrue(provider.is_local_endpoint)

    def test_localhost_suffix_is_not_loopback(self):
        with self.assertRaisesRegex(ProviderError, 'allow_remote=true'):
            create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                             'base_url': 'http://localhost.example.invalid/v1'})

    def test_openai_request_counts_and_raw_text(self):
        provider = create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                                    'base_url': 'http://127.0.0.1:8765/v1', 'seed': 7})
        payload = {'choices': [{'message': {'content': 'deliberately malformed JSON'}}],
                   'usage': {'prompt_tokens': 13, 'completion_tokens': 5}}
        with patch('urllib.request.urlopen', return_value=response(payload)) as request:
            result = provider.complete(self.messages)
        sent = json.loads(request.call_args.args[0].data)
        self.assertEqual(sent['response_format'], {'type': 'json_object'})
        self.assertEqual(sent['seed'], 7)
        self.assertEqual(result['content'], 'deliberately malformed JSON')
        self.assertEqual(result['input_tokens'], 13)
        self.assertEqual(result['output_tokens'], 5)
        self.assertEqual(result['token_count_method'], 'api_usage')
        self.assertEqual(result['raw']['_execution_location'], 'loopback')

    def test_gemini_payload_and_usage(self):
        provider = create_provider({'provider': 'gemini', 'model': 'synthetic', 'allow_remote': True})
        payload = {'candidates': [{'content': {'parts': [{'text': '{"ok":true}'}]}}],
                   'usageMetadata': {'promptTokenCount': 17, 'candidatesTokenCount': 6}}
        with patch('urllib.request.urlopen', return_value=response(payload)) as request:
            result = provider.complete(self.messages)
        sent = json.loads(request.call_args.args[0].data)
        self.assertEqual(sent['systemInstruction']['parts'][0]['text'], 'Return JSON.')
        self.assertEqual(sent['contents'][0]['role'], 'user')
        self.assertEqual(sent['generationConfig']['responseMimeType'], 'application/json')
        self.assertEqual(result['input_tokens'], 17)
        self.assertEqual(result['output_tokens'], 6)

    def test_missing_usage_is_labelled_estimate(self):
        provider = create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                                    'base_url': 'http://127.0.0.1:8765/v1'})
        with patch('urllib.request.urlopen', return_value=response({'choices': [{'message': {'content': '{}'}}]})):
            result = provider.complete(self.messages)
        self.assertIn('estimated', result['token_count_method'])

    def test_transient_429_is_bounded_and_retried(self):
        provider = create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                                    'base_url': 'http://127.0.0.1:8765/v1', 'retries': 1})
        error = urllib.error.HTTPError('http://synthetic', 429, 'limit', {'Retry-After': '0'}, None)
        good = response({'choices': [{'message': {'content': '{}'}}]})
        with patch('urllib.request.urlopen', side_effect=[error, good]) as request, patch('time.sleep') as sleep:
            result = provider.complete(self.messages)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result['content'], '{}')
        sleep.assert_called_once_with(0.0)

    def test_terminal_error_does_not_expose_response_or_key(self):
        provider = create_provider({'provider': 'openai_compatible', 'model': 'synthetic',
                                    'base_url': 'http://127.0.0.1:8765/v1', 'retries': 0})
        error = urllib.error.HTTPError('http://synthetic?key=secret', 401, 'secret', {},
                                       io.BytesIO(b'private screenplay'))
        with patch('urllib.request.urlopen', side_effect=error), self.assertRaises(ProviderError) as raised:
            provider.complete(self.messages)
        self.assertIn('HTTP 401', str(raised.exception))
        self.assertNotIn('secret', str(raised.exception))
        self.assertNotIn('private screenplay', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
