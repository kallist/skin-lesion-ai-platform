/** Shared API types — mirrors backend/app/schemas/__init__.py */

export type Prediction = 'benign' | 'malignant';

export interface Probabilities {
  benign: number;
  malignant: number;
}

export interface User {
  id: number;
  email: string;
  username: string;
  full_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  user: User;
  csrf_token: string;
  message: string;
}

export interface Detection {
  id: number;
  prediction: Prediction;
  confidence: number;
  probabilities: Probabilities;
  model_version: string;
  original_filename: string;
  image_available: boolean;
  disclaimer: string;
  advice: string;
  created_at: string;
}

export interface DetectionListItem {
  id: number;
  prediction: Prediction;
  confidence: number;
  probabilities: Probabilities;
  model_version: string;
  original_filename: string;
  image_available: boolean;
  created_at: string;
}

export interface DetectionPage {
  items: DetectionListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ModelInfo {
  model_version: string;
  architecture: string;
  input_size: number;
  class_names: string[];
  class_mapping: Record<string, number>;
  trained_at: string;
  device: string;
  calibration: string;
  disclaimer: string;
  available: boolean;
  best_val_metric: Record<string, number | string>;
}

export interface Health {
  status: 'ok' | 'degraded';
  version: string;
  environment: string;
  database: boolean;
  model: boolean;
  model_version: string | null;
  uptime_seconds: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
