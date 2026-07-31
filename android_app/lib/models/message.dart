/// A single message in a session conversation timeline.
class Message {
  final double timestamp;
  final String type; // user_prompt, assistant_response, tool_use, thinking, pending_approval
  final String? content;
  final String? toolName;
  final String? toolInput;
  final String? toolOutput;
  final int? inputTokens;
  final int? outputTokens;
  final bool skeleton;
  final String? source; // hook event name

  const Message({
    required this.timestamp,
    required this.type,
    this.content,
    this.toolName,
    this.toolInput,
    this.toolOutput,
    this.inputTokens,
    this.outputTokens,
    this.skeleton = false,
    this.source,
  });

  factory Message.fromJson(Map<String, dynamic> json) {
    // Backward compat: "preliminary" was renamed to "skeleton"
    final skeleton = json['skeleton'] as bool? ??
        json['preliminary'] as bool? ??
        false;
    return Message(
      timestamp: (json['timestamp'] as num).toDouble(),
      type: json['type'] as String,
      content: json['content'] as String?,
      toolName: json['tool_name'] as String?,
      toolInput: json['tool_input'] as String?,
      toolOutput: json['tool_output'] as String?,
      inputTokens: json['input_tokens'] as int?,
      outputTokens: json['output_tokens'] as int?,
      skeleton: skeleton,
      source: json['source'] as String?,
    );
  }

  bool get isPrompt => type == 'user_prompt';
  bool get isResponse => type == 'assistant_response';
  bool get isTool => type == 'tool_use';
  bool get isThinking => type == 'thinking';
  bool get isPendingApproval => type == 'pending_approval';
}
