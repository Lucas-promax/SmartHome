"""Agent contracts and tool-stream regressions; no external API or hardware."""
import json
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from agent import agent_service as agent, tools


def response(name=None, arguments="{}", content="", reasoning=""):
    delta = {"content": content, "reasoning_content": reasoning}
    if name:
        delta["tool_calls"] = [{"index": 0, "id": "call_test", "type": "function",
                                "function": {"name": name, "arguments": arguments}}]
    return nullcontext([("data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n").encode(), b"data: [DONE]\n"])


class ToolTests(unittest.TestCase):
    def test_advertised_schemas_match_validation(self):
        self.assertEqual(len(tools.TOOL_DEFINITIONS), 8)
        for definition in tools.TOOL_DEFINITIONS:
            f = definition['function']
            self.assertEqual(f['parameters'], tools.TOOL_ARGUMENT_MODELS[f['name']].model_json_schema())
            self.assertFalse(f['parameters']['additionalProperties'])

    def test_invalid_arguments_cannot_reach_services(self):
        invalid = [
            ('control_device', {'device_id': 'door_main', 'action': 'turn_on'}),
            ('control_device', {'device_id': 'light_main', 'action': 'set_level'}),
            ('control_device', {'device_id': 'fan_main', 'action': 'turn_on', 'value': 'high'}),
            ('set_person_authorization', {'person_id': True, 'action': 'restore'}),
            ('cleanup_logs', {'soruce': 'vision'}),
            ('list_logs', {'limit': 1000}), ('set_theme', {'theme': 'invalid'}),
            ('get_data_analysis', {'after': '2026-11-15'}),
        ]
        with patch.object(tools.log_service, 'cleanup_logs') as cleanup:
            for name, args in invalid:
                with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                    tools.execute_tool(name, args)
            cleanup.assert_not_called()

    def test_control_dispatch_and_log_filters(self):
        with patch.object(tools.home_service, 'control_device', return_value={'command': 'd'}) as control, \
             patch.object(tools.log_service, 'add_operation_log'):
            result = tools.execute_tool('control_device', {'device_id': 'door_main', 'action': 'open'})
            self.assertTrue(result['ok'])
            control.assert_called_once_with('door_main', 'open', None, None)
        with patch.object(tools.log_service, 'list_logs', return_value={}) as logs:
            tools.execute_tool('list_logs', {'source': 'vision'})
            logs.assert_called_once_with({'source': 'vision', 'limit': 20})


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.settings = {**agent.DEFAULT_AGENT_SETTINGS, 'api_key': 'test-only'}
        self.settings_patch = patch.object(agent, 'get_agent_settings', return_value=self.settings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.messages = [{'role': 'user', 'content': 'test'}]

    def test_bad_json_not_treated_as_cleanup_all(self):
        with patch.object(agent, '_urlopen', side_effect=[response('cleanup_logs', '{broken'), response(content='invalid')]), \
             patch.object(agent, 'execute_tool') as execute:
            events = list(agent.chat_stream(self.messages))
            execute.assert_not_called()
            self.assertNotIn('confirm_required', [e['type'] for e in events])

    def test_dangerous_request_only_proposes_confirmation(self):
        with patch.object(agent, '_urlopen', return_value=response('cleanup_logs', '{"source":"vision"}')), \
             patch.object(agent, 'execute_tool') as execute:
            events = list(agent.chat_stream(self.messages))
            execute.assert_not_called()
            self.assertEqual(events[-1]['type'], 'confirm_required')
            self.assertEqual(events[-1]['tool']['arguments'], {'source': 'vision'})

    def test_confirmed_repeat_uses_result_once(self):
        confirmation = {'name': 'cleanup_logs', 'arguments': {'source': 'vision'}}
        with patch.object(agent, '_urlopen', side_effect=[response('cleanup_logs', '{"source":"vision"}'), response(content='done')]), \
             patch.object(agent, 'execute_tool', return_value={'ok': True, 'data': {'total': 1}}) as execute:
            events = list(agent.chat_stream(self.messages, confirmed_tool=confirmation))
            execute.assert_called_once_with('cleanup_logs', {'source': 'vision'})
            self.assertEqual(events[-1]['type'], 'done')

    def test_failed_control_is_not_reported_done(self):
        args = '{"device_id":"door_main","action":"open"}'
        with patch.object(agent, '_urlopen', side_effect=[response('control_device', args), response(content='offline')]), \
             patch.object(agent, 'execute_tool', side_effect=RuntimeError('offline')):
            events = list(agent.chat_stream(self.messages))
            self.assertEqual([e['status'] for e in events if e['type'] == 'tool'], ['running', 'failed'])

    def test_theme_request_and_unknown_client_result(self):
        with patch.object(agent, '_urlopen', return_value=response('set_theme', '{"theme":"dark"}')):
            self.assertEqual(list(agent.chat_stream(self.messages))[-1]['type'], 'client_tool_request')
        with patch.object(agent, '_urlopen') as request:
            events = list(agent.chat_stream(self.messages, client_tool_result={'name': 'invented'}))
            self.assertEqual(events[-1]['type'], 'error')
            request.assert_not_called()

    def test_thinking_tool_continuation_keeps_private_reasoning(self):
        captured = []
        responses = [response('get_home_status', reasoning='private-reasoning'), response(content='**done**')]
        def open_request(request, timeout):
            captured.append(json.loads(request.data))
            return responses.pop(0)
        with patch.object(agent, '_urlopen', side_effect=open_request), \
             patch.object(agent, 'execute_tool', return_value={'ok': True, 'data': {}}):
            events = list(agent.chat_stream(self.messages))
        assistant = next(m for m in captured[1]['messages'] if m.get('tool_calls'))
        self.assertEqual(assistant['reasoning_content'], 'private-reasoning')
        self.assertNotIn('private-reasoning', json.dumps(events))
        self.settings['thinking_enabled'] = False
        self.assertEqual(agent._build_payload(self.settings, self.messages)['thinking']['type'], 'disabled')

    def test_fragmented_tool_name_and_public_history(self):
        calls = []
        agent._merge_tool_call_delta(calls, [{'index': 0, 'function': {'name': 'get_home_', 'arguments': '{'}}])
        agent._merge_tool_call_delta(calls, [{'index': 0, 'function': {'name': 'status', 'arguments': '}'}}])
        self.assertEqual(calls[0]['function'], {'name': 'get_home_status', 'arguments': '{}'})
        payload = agent._build_payload(self.settings, self.messages + [{'role': 'assistant', 'content': 'old answer'}])
        self.assertEqual(payload['messages'][-1]['role'], 'user')
        self.assertIn('old answer', payload['messages'][-1]['content'])


if __name__ == '__main__':
    unittest.main()
