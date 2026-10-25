"""Add read-only timing and DX12 descriptor counters to a derived engine fork."""
from pathlib import Path
import argparse,json,hashlib

PROFILER_API='''
	// BVR diagnostic API: read completed engine ranges, without UI scraping.
	// GPU results are delayed by the engine frame buffers and use its smoothing.
	std::map<std::string, double> GetTimingSnapshot(bool gpu)
	{
		std::lock_guard<std::mutex> guard(lock);
		std::map<std::string, double> result;
		for (const auto& item : ranges)
		{
			const auto& range = item.second;
			if (range.IsCPURange() != gpu && range.avg_counter > 0)
				result[range.name] += range.time;
		}
		return result;
	}
'''
DESCRIPTOR_API='''uint64_t bvr_bindless_resource_failures=0;
uint64_t bvr_bindless_resource_min_free=BINDLESS_RESOURCE_CAPACITY;
std::map<std::string,uint64_t> GetBvrDescriptorState()
{
    auto* device=static_cast<GraphicsDevice_DX12*>(GetDevice());
    auto& handler=*device->allocationhandler;
    std::scoped_lock guard(handler.destroylocker);
    return {{"capacity",BINDLESS_RESOURCE_CAPACITY},{"free",handler.free_bindless_res.size()},
        {"pending_release",handler.destroyer_bindless_res.size()},
        {"allocation_failures",bvr_bindless_resource_failures},{"minimum_free",bvr_bindless_resource_min_free}};
}
'''

def replace_once(text,old,new,count=1):
    if text.count(old)!=count:raise ValueError('Pinned engine anchor changed: '+old[:70])
    return text.replace(old,new)

def prepare_engine(engine):
    engine=Path(engine).resolve()
    if not (engine/'bvr-wide-primitive.json').is_file():
        raise ValueError('Diagnostics must be installed into an explicitly prepared independent engine fork')
    profiler=engine/'WickedEngine/wiProfiler.cpp';dx12=engine/'WickedEngine/wiGraphicsDevice_DX12.cpp'
    text=profiler.read_text(encoding='utf8')
    if 'GetTimingSnapshot(bool gpu)' not in text:
        text=replace_once(text,'#include <sstream>','#include <sstream>\n#include <map>')
        text=replace_once(text,'\twi::unordered_map<size_t, Range> ranges;', '\twi::unordered_map<size_t, Range> ranges;\n'+PROFILER_API)
        profiler.write_text(text,encoding='utf8')
    text=dx12.read_text(encoding='utf8')
    if 'GetBvrDescriptorState()' not in text:
        text=replace_once(text,'namespace wi::graphics\n{\n','namespace wi::graphics\n{\n'+DESCRIPTOR_API)
        anchor='\t\t\t\tallocationhandler->free_bindless_res.pop_back();\n\t\t\t}\n\t\t\tallocationhandler->destroylocker.unlock();'
        replacement=anchor.replace('\n\t\t\tallocationhandler->destroylocker.unlock();',
            '\n\t\t\telse ++bvr_bindless_resource_failures;\n\t\t\tbvr_bindless_resource_min_free=std::min<uint64_t>(bvr_bindless_resource_min_free,allocationhandler->free_bindless_res.size());\n\t\t\tallocationhandler->destroylocker.unlock();')
        text=replace_once(text,anchor,replacement,3);dx12.write_text(text,encoding='utf8')
    manifest={'schema_version':1,'api':'bvr_runtime_diagnostics_v1','files':[
        {'file':str(file.relative_to(engine)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()} for file in [profiler,dx12]],
        'scope':'Read-only buffered GPU/CPU profiler snapshots and descriptor failure/low-water counters; descriptor capacity and allocation policy are unchanged.'}
    (engine/'bvr-runtime-diagnostics.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True)
    print(json.dumps(prepare_engine(p.parse_args().engine),indent=2))
