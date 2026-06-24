//! Pipeline v2 input/output models.

pub mod enriched;
pub mod extracted;
pub mod persisted;
pub mod segmented;
pub mod source;

// NOTE: These globs expose the public model surface of each submodule.
// They are intentionally re-exported here while submodules are still being
// populated in subsequent tasks. Remove this allow once all modules have exports.
#[allow(unused_imports)]
pub use enriched::*;
#[allow(unused_imports)]
pub use extracted::*;
#[allow(unused_imports)]
pub use persisted::*;
#[allow(unused_imports)]
pub use segmented::*;
pub use source::*;
