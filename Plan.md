Context 在消息接收的时候就进行解析，不再放到 MaiMessage 里面，由消息注册的时候直接进去注册
- [ ] 实现`update_chat_context`方法，主要关注`format_info`


1. **预计不对发送的时候进行`accept_format`的格式判断**，希望所有消息适配器接收的时候做一下不兼容内容主动丢弃
2. 在发送消息的时候进行`accept_format`的判断，判断不兼容内容是否存在，如果存在则丢弃掉

- [ ] 实现 status_api

