import {useEffect,useState} from 'react';
import {collectionStore,loadCollections,saveTemplate} from '../stores/collections';
import {specimenStore,loadSpecimens,saveSpecimen} from '../stores/specimens';
import {authStore,canEdit} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import PageHeading from '../components/common/PageHeading';
import ErrorNotice from '../components/common/ErrorNotice';
import CollectionSelect from '../components/CollectionSelect';
import ShapeCanvas from '../components/ShapeCanvas';
import type {Specimen} from '../types/domain';

export default function Sources(){
  const {items,templates,selected}=collectionStore.use(),{items:specimens}=specimenStore.use(),{user}=authStore.use();
  const {busy,error,perform}=useTask(),[tab,setTab]=useState('specimens'),[edit,setEdit]=useState<Specimen|null>(null),[message,setMessage]=useState(''),[stale,setStale]=useState('');
  const collection=items.find(c=>c.id===selected),template=templates.find(t=>t.id===collection?.template_id);
  useEffect(()=>{perform(loadCollections)},[]);
  useEffect(()=>{if(selected){setEdit(null);setMessage('');setStale('');perform(()=>loadSpecimens(selected))}},[selected]);

  async function submitSpecimen(e:React.FormEvent<HTMLFormElement>){
    e.preventDefault();const f=new FormData(e.currentTarget);
    await perform(async()=>{
      try{
        await saveSpecimen({collection_id:selected,code:f.get('code'),name:f.get('name'),source_note:f.get('source_note'),points:JSON.parse(String(f.get('points'))),template_version:Number(f.get('template_version'))},selected,edit?.id);
        setEdit(null);setStale('');setMessage('角点已保存；既有冻结研究保持原样。');
      }catch(err){
        const msg=err instanceof Error?err.message:String(err);
        if(msg.includes('过期')){setStale(msg);await loadSpecimens(selected);setEdit(null);}
        throw err;
      }
    });
  }

  return <><PageHeading no="02" title="角点与基准" sub="每份8×2坐标，严格保留L1–L8同源顺序；不自动循环重排或反转点序。"/>
  <CollectionSelect/><ErrorNotice error={error}/>
  {message&&<p className="success" role="status">{message}</p>}
  {stale&&<p className="error-text" role="alert">⚠ {stale} 已自动重载当前版本，请按新角点顺序重新编辑。</p>}
  <div className="data-tabs"><button className={tab==='specimens'?'active':''} onClick={()=>setTab('specimens')}>原始裁片 / {specimens.length}</button><button className={tab==='template'?'active':''} onClick={()=>setTab('template')}>同源基准 / {template?.code} v{template?.current_version??1}</button></div>
  {tab==='specimens'?<>
    <details className="edit-fold" open={!!edit}><summary>{edit?'编辑 '+edit.code+'（v'+edit.template_version+' r'+(edit.revision??1)+'）':'＋ 录入一份裁片'}</summary>
      {canEdit(user)?<form className="coordinate-form" key={edit?.id||'new'} onSubmit={submitSpecimen}>
        <input type="hidden" name="template_version" value={edit?.template_version??(template?.current_version??1)}/>
        <div><label>裁片编号<input name="code" defaultValue={edit?.code} minLength={2} required/></label>
        <label>裁片名称<input name="name" defaultValue={edit?.name} minLength={2} required/></label>
        <label>来源说明<input name="source_note" defaultValue={edit?.source_note}/></label>
        <div className="button-row"><button className="primary" disabled={busy}>保存原始角点</button>{edit&&<button type="button" onClick={()=>setEdit(null)}>取消编辑</button>}</div></div>
        <label>按{template?.labels.join(' → ')}顺序的8×2 JSON坐标（当前模板 v{template?.current_version??1}）<textarea name="points" defaultValue={JSON.stringify(edit?.points||template?.points||[],null,2)} rows={12} required/></label>
      </form>:<p className="muted">观察员只读；请形状分析员录入原始点。</p>}
    </details>
    <div className="table-scroll"><table><thead><tr><th>裁片</th><th>来源</th><th>同源点</th><th>模板版本/修订</th><th>首角点 x / y</th>{canEdit(user)&&<th/>}</tr></thead>
      <tbody>{specimens.map(s=><tr key={s.id}><td><b>{s.code}</b><small>{s.name}</small></td><td>{s.source_note}</td><td>{s.points.length} × 2</td><td>v{s.template_version} r{s.revision??1}</td><td>{s.points[0]?.map(x=>x.toFixed(5)).join(' / ')}</td>{canEdit(user)&&<td><button className="small-button" onClick={()=>setEdit(s)}>核对/编辑</button></td>}</tr>)}</tbody></table></div>
    {!specimens.length&&<p className="empty">先选择同源模板，再录入至少两份独立裁片。每份必须有8个有限二维点。</p>}
  </>:template&&<div className="template-spread"><section>
    <h2 className="ruled-title">{template.name} <small>当前生效 v{template.current_version??1}</small></h2>
    <ShapeCanvas shapes={[{points:template.points,label:template.code,color:'var(--red)',emphasis:true}]} labels={template.labels} caption="固定参考朝向与同源顺序；标签/坐标改版须发布新版本，不直接覆盖。"/>
    <aside className="margin-note">{template.convention}<p>角点标签或参考坐标调整会改变同源对应，请到「模板改版」发布新版本并逐点迁移；本页仅可改名称与约定。</p><a className="text-link" href="#/migrations">前往模板改版 ↗</a></aside>
  </section>
  {canEdit(user)&&<form key={template.id} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);perform(async()=>{await saveTemplate({code:f.get('code'),name:f.get('name'),convention:f.get('convention'),labels:template.labels,points:template.points},template.id);setMessage('同源模板名称/约定已保存；角点标签与坐标未改动。')})}}>
    <label>模板编号<input name="code" defaultValue={template.code} required/></label>
    <label>模板名称<input name="name" defaultValue={template.name} required/></label>
    <label>8个同源标签（只读，改版请到模板改版页）<textarea name="labels" readOnly value={JSON.stringify(template.labels)} rows={4}/></label>
    <label>参考坐标（只读）<textarea name="points" readOnly rows={9} value={JSON.stringify(template.points,null,2)}/></label>
    <label>同源与朝向约定<textarea name="convention" defaultValue={template.convention}/></label>
    <button disabled={busy}>保存名称与约定</button>
  </form>}</div>}
  </>;
}
