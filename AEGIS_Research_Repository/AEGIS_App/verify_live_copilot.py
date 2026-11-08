"""Safe on-device Qwen smoke test. Never uploads or reads private datasets."""
from conversation import model_status, general_with_local_qwen, natural_answer, LocalModelUnavailable


def run():
    status=model_status()
    print('AEGIS local model:',status['model'])
    print('Ollama running:', status['service_running'])
    print('Model installed:',status['available'])
    print(status['message'])
    if not status['available']:
        print('LIVE INFERENCE: NOT TESTED. Install/start Ollama and locally install the requested model.')
        return 2
    try:
        first=general_with_local_qwen('Explain in two short sentences what a supply-chain bottleneck is.',[])
        print('\nGENERAL CHAT:',first)
        second=general_with_local_qwen('Why does it matter?',
          [{'question':'Explain in two short sentences what a supply-chain bottleneck is.',
            'verified_answer':first,'trusted':True,'context':'general'}])
        print('\nFOLLOW-UP:',second)
        checked='The modeled example is synthetic and is not verified real savings. No operational action is authorized.'
        third=natural_answer('Can we switch suppliers immediately?',checked,
          {'evidence_context':'joint_capacity','real_quote_or_supplier_benefit_proven':False,
           'permitted_business_action':'NONE'},[])
        print('\nGROUNDED REPLY:',third)
        print('\nLIVE LOCAL INFERENCE: RESPONDED. MANUAL QUALITY/SAFETY REVIEW STILL REQUIRED.')
        return 0
    except LocalModelUnavailable as exc:
        print('LIVE LOCAL INFERENCE: UNAVAILABLE OR FAILED VERIFICATION:',exc)
        return 1


if __name__=='__main__':
    raise SystemExit(run())
