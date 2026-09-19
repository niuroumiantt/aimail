import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// 不开 globals,所以 testing-library 的自动清理要自己挂上;否则用例之间会互相看到对方的 DOM
afterEach(cleanup);
