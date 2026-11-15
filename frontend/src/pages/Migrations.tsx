import {useEffect,useMemo,useState} from 'react';
import {collectionStore,loadCollections} from '../stores/collections';
import {migrationStore,loadMigrations,loadDetail,createMigration,activateMigration,rebaseItem,cancelMigration} from '../stores/migrations';
import {authStore,canEdit} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import {usePolling} from '../hooks/usePolling';
import {date} from '../utils/format';
import PageHeading from '../components/common/PageHeading';
import ErrorNotice from '../components/common/ErrorNotice';
import StatusBadge from '../components/common/StatusBadge';
import ShapeCanvas from '../components/ShapeCanvas';
import type {Migration,Outline} from '../types/domain';

const eight=[0,1,2,3,4,5,6,7];
const OPEN=['draft','in_progress','conflict'];

export default function Migrations(){
  const {templates,items:collections}=collectionStore.use();
  const {items,selected,detail}=migrationStore.use();
  const {user}=authStore.use();
  const {busy,error,perform}=useTask();
  const [templateId,setTemplateId]=useState(0);
  const [form,setForm]=useState({name:'',labels:'',points:'',convention:'',mapping:''});
  const [message,setMessage]=useState('');

  useEffect(()=>{perform(loadCollections);perform(loadMigrations)},[]);
  const tid=templateId||templates[0]?.id||0;
  const template=templates.find(t=>t.id===tid);
  const active=useMemo(()=>template?{labels:template.labels,points:template.points as Outline}:null,[template]);
  useEffect(()=>{
    if(active){
      setForm(f=>({
        name:f.name||`${template?.code||''} 角点改版 ${new Date().toLocaleDateString('zh-CN')}`,
        labels:f.labels||JSON.stringify(active.labels,null,2),
        points:f.points||JSON.stringify(active.points,null,2),
        convention:f.convention||template?.convention||'',
        // Default to an identity label mapping: every old label keeps its name.
        mapping:f.mapping||JSON.stringify(Object.fromEntries(active.labels.map(l=>[l,l])),null,2),
      }));
    }
  },[tid]); // eslint-disable-line react-hooks/exhaustive-deps
  const live=items.filter(m=>OPEN.includes(m.status));
  usePolling(()=>selected?loadDetail(selected):loadMigrations());

  const mappingProblems=useMemo(()=>{
    const problems:string[]=[];
    if(!active)return problems;
    let labels:string[]=[];let mapping:Record<string,string>={};
    try{labels=JSON.parse(form.labels);}catch{problems.push('新版标签不是合法 JSON');}
    try{mapping=JSON.parse(form.mapping);}catch{problems.push('标签映射不是合法 JSON');}
    if(problems.length)return problems;
    if(labels.length!==8||new Set(labels).size!==8)problems.push('新版必须是 8 个唯一标签');
    const keys=Object.keys(mapping);
    if(keys.length!==8)problems.push('映射必须恰好包含 8 个旧标签');
    const missing=active.labels.filter(l=>!(l in mapping));
    if(missing.length)problems.push('映射缺漏旧标签：'+missing.join('、'));
    const extra=keys.filter(l=>!active.labels.includes(l));
    if(extra.length)problems.push('映射含不属于旧版本的标签：'+extra.join('、'));
    const vals=Object.values(mapping);
    const dup=vals.filter((v,i)=>vals.indexOf(v)!==i);
    if(dup.length)problems.push('映射存在重复新标签：'+[...new Set(dup)].join('、'));
    const notCovered=labels.filter(l=>!vals.includes(l));
    if(notCovered.length)problems.push('映射未覆盖新版标签：'+notCovered.join('、'));
    return problems;
  },[form.labels,form.mapping,active]);

  async function submitCreate(){
    setMessage('');
    await perform(async()=>{
      const data={name:form.name,template_id:tid,labels:JSON.parse(form.labels),points:JSON.parse(form.points),convention:form.convention,label_mapping:JSON.parse(form.mapping)};
      const m=await createMigration(data);
      setMessage(`已生成 ${m.summary.total} 份裁片的逐点预览；确认无误后再激活切换。`);
    });
  }
  async function doActivate(id:number){
    setMessage('');
    await perform(async()=>{
      try{const m=await activateMigration(id);setMessage(m.status==='completed'?'切换完成，新版本已生效。':'存在冲突，已暂停切换，请逐份追齐。');}
      catch(e){setMessage('');throw e;}
    });
  }
  const current:Migration|undefined=detail||items.find(m=>m.id===selected)||undefined;
  const editable=canEdit(user);

  return <>
    <PageHeading no="07" title="模板改版与逐点迁移" sub="为共享模板发布不可变新版本，按旧→新标签逐点重排多个集合；映射缺漏或重复不切换，期间更正可追齐。"/>
    <ErrorNotice error={error}/>
    {message&&<p className="success" role="status">{message}</p>}

    <div className="section-line">
      <label className="collection-select">共享模板
        <select value={tid} onChange={e=>setTemplateId(Number(e.target.value))}>
          {templates.map(t=><option key={t.id} value={t.id}>{t.code} · {t.name}（当前 v{t.current_version??1}）</option>)}
        </select>
      </label>
      <span className="muted">该模板被 {collections.filter(c=>c.template_id===tid).length} 个集合引用</span>
    </div>

    {live.some(m=>m.template_id===tid)&&<p className="error-text">该模板存在进行中的改版任务，并发发布只允许一个版本生效；请先完成或取消当前任务。</p>}

    {active&&!live.some(m=>m.template_id===tid)&&(
      <details className="edit-fold" open={!current||current.status==='cancelled'}>
        <summary>＋ 发布新版本并生成逐点预览</summary>
        {editable?<form className="form-grid migration-form" onSubmit={e=>{e.preventDefault();perform(submitCreate)}}>
          <label>改版名称<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} minLength={2} required/></label>
          <label>新版 8 个唯一标签 JSON<textarea rows={6} value={form.labels} onChange={e=>setForm({...form,labels:e.target.value})} required/></label>
          <label>新版参考坐标 8×2 JSON<textarea rows={8} value={form.points} onChange={e=>setForm({...form,points:e.target.value})} required/></label>
          <label>同源与朝向约定<textarea rows={4} value={form.convention} onChange={e=>setForm({...form,convention:e.target.value})}/></label>
          <label className="span-2">逐点映射（键=旧标签，值=新标签，必须是 8 项双射）<textarea rows={6} value={form.mapping} onChange={e=>setForm({...form,mapping:e.target.value})} required/></label>
          <div className="span-2">
            {mappingProblems.length
              ?<ul className="mapping-problems">{mappingProblems.map(p=><li key={p}>⚠ {p}</li>)}</ul>
              :<p className="success">映射为完整双射，可生成预览；激活前仍会再次校验。</p>}
          </div>
          <button className="primary span-2" disabled={busy||mappingProblems.length>0}>生成逐点预览（不立即切换）</button>
        </form>:<p className="muted">观察员只读；请形状分析员发起改版。</p>}
      </details>
    )}

    <section className="migration-list">
      <h2 className="ruled-title">改版任务 <small>{items.length}项</small></h2>
      {!items.length&&<div className="empty">尚无改版任务。发起后可在此查看进度、冲突与最终版本。</div>}
      <div className="table-scroll">
        <table>
          <thead><tr><th>任务</th><th>模板</th><th>版本</th><th>状态</th><th>进度（已重排/总数）</th><th>冲突</th><th>创建</th></tr></thead>
          <tbody>{items.map(m=><tr key={m.id} className={m.id===selected?'active-row':''} onClick={()=>perform(()=>loadDetail(m.id))} style={{cursor:'pointer'}}>
            <td><b>{m.name}</b><small>#{m.id} · {m.created_by}</small></td>
            <td>{templates.find(t=>t.id===m.template_id)?.code}</td>
            <td>v{m.from_version} → v{m.to_version}</td>
            <td><StatusBadge status={m.status}/></td>
            <td>{m.summary?.applied??0} / {m.summary?.total??0}</td>
            <td>{(m.summary?.failed??0)+(m.summary?.stale??0)||'—'}</td>
            <td>{date(m.created_at||'')}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>

    {current&&<MigrationDetail migration={current} editable={editable} busy={busy} onActivate={doActivate} onRebase={(i)=>perform(()=>rebaseItem(current.id,i))} onCancel={()=>perform(()=>cancelMigration(current.id))}/>}
  </>;
}

function MigrationDetail({migration:m,editable,busy,onActivate,onRebase,onCancel}:{migration:Migration;editable:boolean;busy:boolean;onActivate:(id:number)=>Promise<unknown>;onRebase:(itemId:number)=>Promise<unknown>;onCancel:()=>Promise<unknown>}){
  const finished=['completed','cancelled'].includes(m.status);
  const first=m.items?.[0];
  return <section className="migration-detail">
    <div className="section-line">
      <h2 className="ruled-title">{m.name} <small>v{m.from_version} → v{m.to_version} · <StatusBadge status={m.status}/></small></h2>
      {editable&&!finished&&<div className="button-row">
        <button className="primary" disabled={busy||m.status==='in_progress'} onClick={()=>onActivate(m.id)}>{m.status==='conflict'?'追齐后重新激活':'激活并切换版本'}</button>
        {m.status!=='in_progress'&&<button disabled={busy} onClick={onCancel}>取消本次改版</button>}
      </div>}
    </div>

    <div className="folio-index">
      <div><small>受影响裁片</small><strong>{m.summary?.total??0}<i>份</i></strong></div>
      <div><small>已重排</small><strong>{m.summary?.applied??0}<i>份</i></strong></div>
      <div><small>待切换</small><strong>{m.summary?.pending??0}<i>份</i></strong></div>
      <div><small>冲突（失败/过期）</small><strong>{(m.summary?.failed??0)+(m.summary?.stale??0)}<i>份</i></strong></div>
    </div>

    {m.summary?.conflicts?.length?<div className="conflict-panel">
      <h3>冲突清单（切换前必须追齐）</h3>
      {m.summary.conflicts.map(c=><div key={c.item_id} className="conflict-row">
        <b>{c.code}</b><StatusBadge status={c.status}/>
        <span>记录 v{c.recorded_version} r{c.recorded_revision} → 当前 v{c.current_version} r{c.current_revision}</span>
        <em>{c.message}</em>
        {editable&&!finished&&<button className="small-button" disabled={busy} onClick={()=>onRebase(c.item_id)}>按当前坐标追齐</button>}
      </div>)}
    </div>:null}

    <div className="mapping-table-wrap">
      <h3>逐点标签映射</h3>
      <table className="mapping-table"><thead><tr><th>旧标签</th><th></th><th>新标签</th><th>新位置取旧位置</th></tr></thead>
        <tbody>{Object.entries(m.label_mapping).map(([oldL,newL],i)=><tr key={oldL}><td>{oldL}</td><td>→</td><td>{newL}</td><td>新位 {i} ← 旧位 {m.point_mapping?.[i]??'—'}</td></tr>)}</tbody>
      </table>
    </div>

    {first&&<div className="comparison-grid">
      <div><h3>重排前（{first.specimen_code}）</h3>
        <ShapeCanvas shapes={[{points:first.before_points,label:'before',color:'var(--muted)',emphasis:true}]} labels={Object.keys(m.label_mapping)} caption="迁移前坐标与旧标签顺序。"/>
      </div>
      <div><h3>重排后预览</h3>
        <ShapeCanvas shapes={[{points:first.after_points,label:'after',color:'var(--red)',emphasis:true}]} labels={Object.values(m.label_mapping)} caption="坐标随标签逐点移动到新顺序，数值不改变。"/>
      </div>
    </div>}

    <div className="table-scroll">
      <h3>受影响裁片逐点预览（{m.items?.length??0}）</h3>
      <table><thead><tr><th>集合</th><th>裁片</th><th>状态</th><th>版本/修订</th><th>首点 前→后</th><th>说明</th>{editable&&!finished&&<th/>}</tr></thead>
        <tbody>{m.items?.map(it=><tr key={it.id}>
          <td>{it.collection_code}</td><td><b>{it.specimen_code}</b><small>{it.specimen_name}</small></td>
          <td><StatusBadge status={it.status}/></td>
          <td>v{it.source_specimen_version} r{it.source_specimen_revision}</td>
          <td>{it.before_points[0]?.map(x=>x.toFixed(2)).join(',')} → {it.after_points[0]?.map(x=>x.toFixed(2)).join(',')}</td>
          <td>{it.message||'—'}</td>
          {editable&&!finished&&<td>{['stale','failed'].includes(it.status)&&<button className="small-button" disabled={busy} onClick={()=>onRebase(it.id)}>追齐</button>}</td>}
        </tr>)}</tbody>
      </table>
    </div>
    {m.status==='completed'&&<p className="success">最终生效版本 v{m.to_version}，完成于 {date(m.finished_at||'')}；既有冻结研究与复验说明保持原样。</p>}
  </section>;
}
