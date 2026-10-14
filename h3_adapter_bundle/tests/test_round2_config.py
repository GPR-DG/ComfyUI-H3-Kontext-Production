"""Round-2 regressions: invalid config must fail before it is persisted/used."""
import tempfile
from pathlib import Path
import unittest
from h3_adapter.config import ConfigError, ConfigStore, validate
from test_config import config


class Round2ConfigTests(unittest.TestCase):
    def reject_provider(self, field, value):
        cfg=config(); cfg['providers'][0][field]=value
        self.reject_config(cfg)

    def reject_config(self, cfg):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / 'providers.json')
            store.save(config())
            with self.assertRaises(ConfigError):
                store.save(cfg)
            self.assertEqual(store.load(), config())

    def test_key_env_must_be_string_even_when_falsey(self):
        for value in (None,False,0,[],{}):
            with self.subTest(value=value):self.reject_provider('key_env',value)
        for value in ('','H3_TEST_KEY'):
            cfg=config();cfg['providers'][0]['key_env']=value;validate(cfg)

    def test_response_limit_matches_protocol_positive_integer_contract(self):
        for value in (5.5,True,0,-1,float('inf')):
            with self.subTest(value=value):self.reject_provider('max_response_bytes',value)
        self.assertIsNotNone(validate(config()))

    def test_allowed_params_contain_only_strings(self):
        for value in ([[]],[{}],[None],[3],[False]):
            with self.subTest(value=value):
                cfg=config();cfg['providers'][0]['models']['background-edit']['allowed_params']=value
                self.reject_config(cfg)
        cfg=config();cfg['providers'][0]['models']['background-edit']['allowed_params']=['size'];validate(cfg)

    def test_async_states_are_string_lists_not_substring_containers(self):
        for name in ('success','failure'):
            for value in ('succeeded',None,{},[None],[1],['']):
                with self.subTest(name=name,value=value):
                    cfg=config();cfg['providers'][0]['async']=self.async_config();cfg['providers'][0]['async'][name]=value
                    self.reject_config(cfg)

    def test_async_success_and_failure_do_not_overlap(self):
        cfg=config();cfg['providers'][0]['async']=self.async_config()
        cfg['providers'][0]['async'].update(success=['done'],failure=['done'])
        self.reject_config(cfg)

    def test_async_max_polls_and_interval_reject_boolean(self):
        for name in ('max_polls','poll_interval'):
            cfg=config();cfg['providers'][0]['async']=self.async_config();cfg['providers'][0]['async'][name]=True
            with self.subTest(name=name):
                self.reject_config(cfg)

    def test_priority_remains_positive_finite_nonboolean(self):
        for value in (True,0,-1,float('nan'),float('inf')):
            with self.subTest(value=value):self.reject_provider('priority',value)

    def test_async_valid_defaults_and_empty_failure_states(self):
        cfg=config();cfg['providers'][0]['async']=self.async_config();validate(cfg)
        cfg['providers'][0]['async']['failure']=[];validate(cfg)

    def test_global_timeout_cannot_be_null(self):
        cfg=config();cfg['timeout_seconds']=None
        self.reject_config(cfg)

    def test_global_cooldown_cannot_be_null(self):
        cfg=config();cfg['cooldown_seconds']=None
        self.reject_config(cfg)

    def test_global_auto_failover_is_boolean_not_truthy_string(self):
        for value in ('false','true',0,None):
            with self.subTest(value=value):
                cfg=config();cfg['auto_failover']=value
                self.reject_config(cfg)
        for value in (False,True):
            cfg=config();cfg['auto_failover']=value;cfg['max_total_cost']=None
            validate(cfg)

    @staticmethod
    def async_config():
        return {'task_id_path':'id','poll_path':'/tasks/{task_id}','status_path':'status'}


if __name__=='__main__':unittest.main()
