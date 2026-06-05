import sys, os
sys.path.insert(0, 'ref')
sys.argv = ['gen_closure_tools.py', '--source', 'src-tauri/src/core/agent/fs.rs', '--module-path', 'crate::core::agent::fs', '--out', 'C:/tmp/closure_gen/fs_rig.rs']
os.makedirs('C:/tmp/closure_gen', exist_ok=True)
import gen_closure_tools
gen_closure_tools.main()
