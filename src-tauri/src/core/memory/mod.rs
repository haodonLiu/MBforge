//! Memory subsystem — persistent memory, skills, trajectory.
//!
//! Re-exports the public API at the `memory` namespace so callers can
//! write `use crate::core::memory::MemoryManager` instead of the longer
//! `crate::core::memory::memory::MemoryManager`.

pub mod memory;
pub mod skills;
pub mod trajectory;

pub use memory::MemoryManager;
pub use skills::SkillsManager;
pub use trajectory::TrajectoryTracker;
