#![allow(dead_code)]
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::core::config::constants::{PROJECT_META_DIR, TRAJECTORY_DIR, TRAJECTORY_FILE};
use crate::core::helpers::now_rfc3339;

const MAX_STEPS: usize = 500;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrajectoryStep {
    pub step_type: String,
    pub uri: String,
    #[serde(default)]
    pub query: String,
    #[serde(default)]
    pub result_count: usize,
    #[serde(default)]
    pub top_results: Vec<String>,
    #[serde(default)]
    pub duration_ms: f64,
    #[serde(default = "now_rfc3339")]
    pub timestamp: String,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct TrajectoryData {
    steps: Vec<TrajectoryStep>,
    updated_at: String,
}

pub struct TrajectoryTracker {
    path: PathBuf,
    steps: Vec<TrajectoryStep>,
}

impl TrajectoryTracker {
    pub fn new(project_root: &Path) -> Self {
        let path = project_root
            .join(PROJECT_META_DIR)
            .join(TRAJECTORY_DIR)
            .join(TRAJECTORY_FILE);
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let steps = Self::load_from_file(&path);
        Self { path, steps }
    }

    fn load_from_file(path: &Path) -> Vec<TrajectoryStep> {
        let data: Option<TrajectoryData> = crate::core::helpers::load_json(path);
        data.map(|d| d.steps).unwrap_or_default()
    }

    pub fn save(&self) {
        let data = TrajectoryData {
            steps: self.steps.clone(),
            updated_at: now_rfc3339(),
        };
        let _ = crate::core::helpers::save_json(&self.path, &data);
    }

    pub fn add_step(&mut self, step: TrajectoryStep) {
        self.steps.push(step);
        if self.steps.len() > MAX_STEPS {
            self.steps = self.steps.split_off(self.steps.len() - MAX_STEPS);
        }
        self.save();
    }

    pub fn record_search(
        &mut self,
        query: &str,
        count: usize,
        results: Vec<String>,
        duration_ms: f64,
    ) {
        self.add_step(TrajectoryStep {
            step_type: "search".into(),
            uri: format!(
                "viking://kb/search?q={}",
                &query[..query.floor_char_boundary(100)]
            ),
            query: query.to_string(),
            result_count: count,
            top_results: results.into_iter().take(5).collect(),
            duration_ms,
            timestamp: now_rfc3339(),
            metadata: serde_json::json!({}),
        });
    }

    pub fn record_tool(&mut self, name: &str, args: &serde_json::Value, summary: &str) {
        self.add_step(TrajectoryStep {
            step_type: "tool".into(),
            uri: format!("viking://tools/{}", name),
            query: {
                let s = args.to_string();
                s[..s.floor_char_boundary(200)].to_string()
            },
            result_count: if summary.is_empty() { 0 } else { 1 },
            top_results: if summary.is_empty() {
                vec![]
            } else {
                vec![summary[..summary.floor_char_boundary(200)].to_string()]
            },
            duration_ms: 0.0,
            timestamp: now_rfc3339(),
            metadata: serde_json::json!({}),
        });
    }

    pub fn get_recent(&self, limit: usize) -> &[TrajectoryStep] {
        let start = self.steps.len().saturating_sub(limit);
        &self.steps[start..]
    }

    pub fn get_summary(&self) -> String {
        if self.steps.is_empty() {
            return "无检索轨迹".into();
        }
        let mut lines = vec![format!("检索轨迹（最近 {} 步）:", self.steps.len())];
        for s in self.steps.iter().rev().take(10) {
            lines.push(format!(
                "  [{}] {} -> {} results",
                s.step_type, s.uri, s.result_count
            ));
        }
        lines.join("\n")
    }

    pub fn export_tool_sequence(&self) -> Vec<String> {
        self.steps
            .iter()
            .filter(|s| s.step_type == "tool")
            .map(|s| s.uri.split('/').last().unwrap_or("").to_string())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trajectory_tracker() {
        let dir = tempfile::tempdir().unwrap();
        let mut tracker = TrajectoryTracker::new(dir.path());
        tracker.record_search("test query", 5, vec!["result1".into()], 100.0);
        assert_eq!(tracker.get_recent(10).len(), 1);
        assert!(!tracker.get_summary().is_empty());
    }
}
