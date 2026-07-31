/// A single message in a session conversation timeline.
class Message {
  final double timestamp;
  final String type; // user_prompt, assistant_response, tool_use
  final String? content;
  final String? toolName;
  final String? toolInput;
  final String? toolOutput;
  final int? inputTokens;
  final int? outputTokens;

  const Message({
    required this.timestamp,
    required this.type,
    this.content,
    this.toolName,
    this.toolInput,
    this.toolOutput,
    this.inputTokens,
    this.outputTokens,
  });

  factory Message.fromJson(Map<String, dynamic> json) {
    return Message(
      timestamp: (json['timestamp'] as num).toDouble(),
      type: json['type'] as String,
      content: json['content'] as String?,
      toolName: json['tool_name'] as String?,
      toolInput: json['tool_input'] as String?,
      toolOutput: json['tool_output'] as String?,
      inputTokens: json['input_tokens'] as int?,
      outputTokens: json['output_tokens'] as int?,
    );
  }

  bool get isPrompt => type == 'user_prompt';
  bool get isResponse => type == 'assistant_response';
  bool get isTool => type == 'tool_use';
}
