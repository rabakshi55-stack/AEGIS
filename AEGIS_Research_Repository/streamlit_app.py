"""Public AEGIS demonstration. Deploy with Streamlit Community Cloud."""
import streamlit as st
import plotly.graph_objects as go
import html
import os
from cloud_engine import CloudWorkspace, SAMPLE, ROLES
from hosted_copilot import GroqClient
from adaptive_charts import recommend
from custom_charts import CHART_TYPES, AGGREGATIONS, DATE_GRAINS, SORTS
from app import STORE, research_answer, get_joint_evidence
from model_registry import collect_report

st.set_page_config(page_title='AEGIS | Decision Intelligence', page_icon='🛡️', layout='wide')
if 'aegis_workspace' not in st.session_state:
    st.session_state.aegis_workspace = CloudWorkspace()
    st.session_state.upload_epoch = 0
w = st.session_state.aegis_workspace
st.sidebar.title('AEGIS')
st.sidebar.caption('SUPPLY CHAIN DECISION INTELLIGENCE')
page=st.sidebar.radio('Workspace',['Data','Visualizations','Decision Copilot','Research evidence'])
st.sidebar.info('Online research demonstration · AEGIS hosted AI or standard evidence-grounded analytics. Local SQLite and private Ollama remain in the local edition.')
try:
    hosted_key = str(st.secrets.get('GROQ_API_KEY', os.getenv('GROQ_API_KEY', ''))).strip()
except Exception:
    hosted_key = os.getenv('GROQ_API_KEY','').strip()
mode = st.sidebar.radio('Copilot mode', ['AEGIS AI (GPT-OSS)','Standard analytics'], index=0 if hosted_key else 1)
consent = False
if mode == 'AEGIS AI (GPT-OSS)':
    if not hosted_key:
        st.sidebar.warning('Hosted AI is not configured. The app owner must add GROQ_API_KEY in Streamlit Secrets.')
    else:
        consent = st.sidebar.checkbox('I agree to send my questions, column names, conversation and bounded calculation results to Groq. I will use only public or authorized non-sensitive data.', value=False)
client = GroqClient(hosted_key) if hosted_key and consent and mode == 'AEGIS AI (GPT-OSS)' else None

def active_client():
    if mode == 'AEGIS AI (GPT-OSS)' and client is None:
        raise ValueError('Configure hosted AI and accept its data-sharing notice, or select Standard analytics.')
    return client
st.sidebar.caption('© 2026 Arin Bakshi. All Rights Reserved.')
st.title('AEGIS')
st.caption('Explore data. Understand evidence. Support human decisions.')
st.warning('Public hosted demo: use public, fictional or authorized non-sensitive data only. Uploads are processed on the hosting server, not on your device. No operational procurement or certified predictions.')

render_counter = 0
def render(c, auto=False):
    global render_counter
    render_counter += 1
    typ=c['type'] if auto else c['chart_type']; title=c['title'] if auto else f"{c['y'] or 'Record count'} by {c['x']}"
    st.subheader(title)
    if c.get('points'):
        p=c['points']; fig=go.Figure(go.Scatter(x=[v['x'] for v in p],y=[v['y'] for v in p],mode='markers'))
    else:
        v=c.get('values',[]); labels=[html.escape(str(x['label'])) for x in v]; ys=[x.get('count',x.get('value')) for x in v]
        if not labels: st.info('No values available.'); return
        if typ=='table': st.dataframe({'Group':[x['label'] for x in v],'Value':ys},use_container_width=True); return
        if typ in ('pie','donut'): fig=go.Figure(go.Pie(labels=labels,values=ys,hole=.45 if typ=='donut' else 0))
        elif typ in ('line','area'): fig=go.Figure(go.Scatter(x=labels,y=ys,mode='lines+markers',fill='tozeroy' if typ=='area' else None))
        elif typ=='horizontal_bar': fig=go.Figure(go.Bar(x=ys,y=labels,orientation='h'))
        else: fig=go.Figure(go.Bar(x=labels,y=ys))
    fig.update_layout(height=350,margin=dict(l=20,r=20,t=20,b=35),showlegend=typ in ('pie','donut'),xaxis=dict(automargin=True),yaxis=dict(automargin=True))
    st.plotly_chart(fig,use_container_width=True,key=f"chart_{render_counter}")
    st.text(c.get('note',c.get('reason','')))
    st.caption(c.get('caution','Descriptive analysis only.'))

if page=='Data':
    st.header('1 · Data')
    f=st.file_uploader('Upload CSV or Excel (.xlsx), up to 5 MiB',type=['csv','xlsx'],key='upload_'+str(st.session_state.upload_epoch))
    a,b,c=st.columns(3)
    if a.button('Load uploaded file',disabled=f is None):
        try: w.upload(f.name,f.getvalue()); st.session_state.pop('last_recommendation',None); st.success('Dataset loaded.')
        except Exception as e: st.error(str(e))
    if b.button('Load fictional example'):
        w.upload('FICTIONAL_example.csv',SAMPLE); st.session_state.pop('last_recommendation',None); st.success('Fictional example loaded.')
    if c.button('Clear dataset and chat'):
        w.clear(); st.session_state.pop('last_recommendation',None); st.session_state.upload_epoch+=1; st.rerun()
    if w.store.dataset:
        p=w.store.status(); st.text(p['filename']); m=st.columns(3); m[0].metric('Rows',p['rows']); m[1].metric('Columns',len(p['columns'])); m[2].metric('Blank cells',sum(x['blank_count'] for x in p['column_profiles']))
        st.dataframe(p['preview'],use_container_width=True)
        with st.expander('Data quality and business-field mapping'):
            st.dataframe(p['column_profiles'],use_container_width=True)
            with st.form('mapping_'+str(w.store.revision)):
                mapping={}
                for role,label in ROLES.items():
                    options=['']+p['columns']; selected=p['mapping'].get(role,''); mapping[role]=st.selectbox(label,options,index=options.index(selected))
                if st.form_submit_button('Apply mapping'):
                    try: w.map(mapping); st.session_state.pop('last_recommendation',None); st.success('Mapping updated; charts and chat reset.'); st.rerun()
                    except Exception as e: st.error(str(e))
        for warning in p['warnings']: st.warning(warning)
    else: st.info('Choose an upload or the fictional example to begin.')
elif page=='Visualizations':
    st.header('2 · Visualizations')
    if not w.store.dataset: st.info('Load data first.')
    else:
        ds=w.store.dataset; charts=recommend(ds)['charts']
        with st.expander('Recommend a chart for an analytical goal',expanded=True):
            q=st.text_input('What do you want to find out?',max_chars=1500)
            if st.button('Recommend a chart',disabled=not q):
                try:
                    r=w.ask('Which chart should I use for this objective: '+q[:1430],hosted_client=active_client()); st.session_state['last_recommendation']=r
                except Exception as e: st.error(str(e))
            r=st.session_state.get('last_recommendation',{}); s=r.get('chart_suggestion')
            if s and s['dataset_revision']==w.store.revision:
                st.text(r['answer'])
                if st.button('Create recommended chart'):
                    try:
                        c=w.use_suggestion(s); render(c,s['kind']=='automatic')
                    except Exception as e: st.error(str(e))
            elif r.get('answer') and not s: st.text(r['answer'])
        st.header('Automatic charts')
        for c in charts: render(c,True)
        st.header('Custom charts')
        with st.form('build_'+str(w.store.revision)):
            t=st.selectbox('Chart type',CHART_TYPES); x=st.selectbox('X field',ds.columns); y=st.selectbox('Y field (optional)',['']+ds.columns); agg=st.selectbox('Aggregation',AGGREGATIONS); grain=st.selectbox('Date grouping',DATE_GRAINS); sort=st.selectbox('Sort',SORTS); limit=st.slider('Max groups/bins',2,100,20)
            if st.form_submit_button('Create chart'):
                try: w.add_chart(dict(chart_type=t,x=x,y=y or None,aggregation=agg,date_grain=grain,sort=sort,limit=limit)); st.success('Chart added.')
                except Exception as e: st.error(str(e))
        for i,opts in enumerate(w.charts):
            render(w.store.chart(opts))
            with st.expander(f'Edit custom chart {i+1}'):
                with st.form(f'edit_{w.store.revision}_{i}'):
                    et=st.selectbox('Chart type',CHART_TYPES,index=CHART_TYPES.index(opts['chart_type'])); ex=st.selectbox('X field',ds.columns,index=ds.columns.index(opts['x'])); ey=st.selectbox('Y field (optional)',['']+ds.columns,index=(['']+ds.columns).index(opts['y'] or '')); ea=st.selectbox('Aggregation',AGGREGATIONS,index=AGGREGATIONS.index(opts['aggregation'])); eg=st.selectbox('Date grouping',DATE_GRAINS,index=DATE_GRAINS.index(opts['date_grain'])); eo=st.selectbox('Sort',SORTS,index=SORTS.index(opts['sort'])); el=st.slider('Max groups/bins',2,100,opts['limit'])
                    if st.form_submit_button('Save chart changes'):
                        try:
                            cfg=dict(chart_type=et,x=ex,y=ey or None,aggregation=ea,date_grain=eg,sort=eo,limit=el)
                            checked=w.store.chart(cfg)
                            w.charts[i]={k:checked[k] for k in cfg}; st.rerun()
                        except Exception as e: st.error(str(e))
            if st.button('Remove chart',key='remove_'+str(i)):
                w.charts.pop(i); st.rerun()
elif page=='Decision Copilot':
    st.header('3 · Decision Copilot')
    if not w.store.dataset and mode == 'Standard analytics': st.info('Load data first, or select AEGIS AI for general conversation.')
    else:
        if st.button('New chat'): w.history.clear(); st.rerun()
        cat=w.catalog(); focus=st.selectbox('Optional chart context',['']+[c['key'] for c in cat],format_func=lambda x: 'No specific chart' if not x else x)
        for i,turn in enumerate(w.history):
            with st.chat_message('user'): st.text(turn['question'])
            with st.chat_message('assistant'):
                st.text(turn['answer']); s=turn.get('chart_suggestion')
                if turn.get('routing_mode') == 'HOSTED_LLM_TOOL_AGENT': st.caption('Hosted AI explanation · calculated evidence is separately displayed; verify interpretations.')
                if s and s['dataset_revision']==w.store.revision:
                    if st.button('Create this chart',key='chat_chart_'+str(i)):
                        try: render(w.use_suggestion(s),s['kind']=='automatic')
                        except Exception as e: st.error(str(e))
        q=st.chat_input('Ask AEGIS about your dataset or a general question',max_chars=1500)
        if q:
            try: w.ask(q,focus or None,hosted_client=active_client()); st.rerun()
            except Exception as e: st.error(str(e))
else:
    st.header('Research evidence')
    st.info('Historical Olist delivery-risk research and fictional sourcing optimization are separate evidence sources. No realized savings or prospective model accuracy is certified.')
    st.write('Frozen research archive status: '+('verified' if STORE.ready else 'not available'))
    with st.expander('Model benchmark and historical limitations'):
        try: st.json(collect_report())
        except Exception as e: st.error(str(e))
    with st.expander('Synthetic capacity allocation'):
        if st.button('Compute archived synthetic experiment'):
            try: st.json(get_joint_evidence())
            except Exception as e: st.error(str(e))
    st.markdown('[AEGIS source repository](https://github.com/rabakshi55-stack/AEGIS)')
st.divider()
st.caption('© 2026 Arin Bakshi. All Rights Reserved. Third-party datasets, models and libraries retain their own terms. Research use only.')
