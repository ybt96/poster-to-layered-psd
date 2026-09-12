import Foundation
import Vision
import AppKit

// 用法: swift ocr.swift <image_path> <out.json>
let args = CommandLine.arguments
let imgPath = args[1]
let outPath = args[2]

guard let img = NSImage(contentsOfFile: imgPath),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("无法读取图片"); exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLanguages = ["zh-Hans", "en"]
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([request])

let W = CGFloat(cg.width), H = CGFloat(cg.height)
var results: [[String: Any]] = []
for obs in request.results ?? [] {
    guard let cand = obs.topCandidates(1).first else { continue }
    let bb = obs.boundingBox  // 归一化, 原点在左下
    let x = bb.origin.x * W
    let y = (1 - bb.origin.y - bb.size.height) * H  // 转为左上原点
    let w = bb.size.width * W
    let h = bb.size.height * H
    results.append([
        "text": cand.string,
        "confidence": cand.confidence,
        "x": x, "y": y, "w": w, "h": h
    ])
}

let data = try JSONSerialization.data(withJSONObject: results, options: .prettyPrinted)
try data.write(to: URL(fileURLWithPath: outPath))
print("识别到 \(results.count) 个文字块 -> \(outPath)")
