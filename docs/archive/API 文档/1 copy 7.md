> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 同步语音合成 HTTP

> 使用本接口，在HTTP网络通信协议下进行同步语音合成。

备用接口地址

`https://api-bj.minimaxi.com/v1/t2a_v2`


## OpenAPI

````yaml api-reference/speech/t2a/api/openapi.json POST /v1/t2a_v2
openapi: 3.1.0
info:
  title: MiniMax T2A API
  description: >-
    MiniMax Text-to-Audio API with support for streaming and non-streaming
    output
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/t2a_v2:
    post:
      tags:
        - Text to Audio
      summary: Text to Audio V2
      operationId: t2aV2
      parameters:
        - name: Content-Type
          in: header
          required: true
          description: 请求体的媒介类型，请设置为 `application/json`，确保请求数据的格式为 JSON
          schema:
            type: string
            enum:
              - application/json
            default: application/json
      requestBody:
        description: ''
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/T2aV2Req'
            examples:
              非流式:
                value:
                  model: speech-2.8-hd
                  text: 今天是不是很开心呀(laughs)，当然了！
                  stream: false
                  voice_setting:
                    voice_id: male-qn-qingse
                    speed: 1
                    vol: 1
                    pitch: 0
                    emotion: happy
                  pronunciation_dict:
                    tone:
                      - 处理/(chu3)(li3)
                      - 危险/dangerous
                  audio_setting:
                    sample_rate: 32000
                    bitrate: 128000
                    format: mp3
                    channel: 1
                  subtitle_enable: false
              流式:
                value:
                  model: speech-2.8-hd
                  text: 今天是不是很开心呀(laughs)，当然了！
                  stream: true
                  voice_setting:
                    voice_id: male-qn-qingse
                    speed: 1
                    vol: 1
                    pitch: 0
                    emotion: happy
                  pronunciation_dict:
                    tone:
                      - 处理/(chu3)(li3)
                      - 危险/dangerous
                  audio_setting:
                    sample_rate: 32000
                    bitrate: 128000
                    format: mp3
                    channel: 1
                  subtitle_enable: false
        required: true
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/T2aV2Resp'
              examples:
                非流式:
                  value:
                    data:
                      audio: <hex编码的audio>
                      status: 2
                    extra_info:
                      audio_length: 9900
                      audio_sample_rate: 32000
                      audio_size: 160323
                      bitrate: 128000
                      word_count: 52
                      invisible_character_ratio: 0
                      usage_characters: 26
                      audio_format: mp3
                      audio_channel: 1
                    trace_id: 01b8bf9bb7433cc75c18eee6cfa8fe21
                    base_resp:
                      status_code: 0
                      status_msg: success
                流式:
                  value:
                    - data:
                        audio: hex编码的audio_chunk1
                        status: 1
                      trace_id: 01b8bf9bb7433cc75c18eee6cfa8fe21
                      base_resp:
                        status_code: 0
                        status_msg: ''
                    - data:
                        audio: hex编码的audio_chunk2
                        status: 1
                      trace_id: 01b8bf9bb7433cc75c18eee6cfa8fe21
                      base_resp:
                        status_code: 0
                        status_msg: ''
                    - data:
                        audio: hex编码的audio
                        status: 2
                      extra_info:
                        audio_length: 6931
                        audio_sample_rate: 32000
                        audio_size: 111789
                        bitrate: 128000
                        word_count: 112
                        invisible_character_ratio: 0
                        usage_characters: 112
                        audio_format: mp3
                        audio_channel: 1
                      trace_id: 04ece790375f3ca2edbb44e8c4c200bf
                      base_resp:
                        status_code: 0
                        status_msg: success
            text/event-stream:
              schema:
                $ref: '#/components/schemas/T2aV2Resp'
              examples:
                流式:
                  value:
                    - data:
                        audio: hex编码的audio_chunk1
                        status: 1
                      trace_id: 01b8bf9bb7433cc75c18eee6cfa8fe21
                      base_resp:
                        status_code: 0
                        status_msg: ''
                    - data:
                        audio: hex编码的audio_chunk2
                        status: 1
                      trace_id: 01b8bf9bb7433cc75c18eee6cfa8fe21
                      base_resp:
                        status_code: 0
                        status_msg: ''
                    - data:
                        audio: hex编码的audio
                        status: 2
                      extra_info:
                        audio_length: 6931
                        audio_sample_rate: 32000
                        audio_size: 111789
                        bitrate: 128000
                        word_count: 112
                        invisible_character_ratio: 0
                        usage_characters: 112
                        audio_format: mp3
                        audio_channel: 1
                      trace_id: 04ece790375f3ca2edbb44e8c4c200bf
                      base_resp:
                        status_code: 0
                        status_msg: success
components:
  schemas:
    T2aV2Req:
      type: object
      required:
        - model
        - text
      properties:
        model:
          type: string
          description: >-
            请求的模型版本，可选范围：`speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`,
            `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`,
            `speech-01-hd`, `speech-01-turbo`.
          enum:
            - speech-2.8-hd
            - speech-2.8-turbo
            - speech-2.6-hd
            - speech-2.6-turbo
            - speech-02-hd
            - speech-02-turbo
            - speech-01-hd
            - speech-01-turbo
        text:
          type: string
          description: >-
            需要合成语音的文本，长度限制小于 10000 字符，若文本长度大于 3000 字符，推荐使用流式输出

            - 段落切换用换行符标记

            - 停顿控制：支持自定义文本之间的语音时间间隔，以实现自定义文本语音停顿时间的效果。使用方式：在文本中增加`<#x#>`标记，`x`
            为停顿时长（单位：秒），范围 [0.01,
            99.99]，最多保留两位小数。文本间隔时间需设置在两个可以语音发音的文本之间，不可连续使用多个停顿标记

            - 行内发音替换：将普通话拼音（带声调数字 `1–5`）或 IPA 音标或粤语拼音（带声调数字
            `1–6`）用英文小括号包裹，可临时覆盖有问题的单词或者多音汉字的发音。
              - `"The word live is pronounced (lɪv) as a verb and (laɪv) as an adjective."`
              - `"This is (he2)平, not (huo4)面."`
              - `"去街市買啲(sung3)。"`
            - 语气词标签：仅当模型选择 `speech-2.8-hd` 或 `speech-2.8-turbo`
            时，支持在文本中插入语气词标签。支持的语气词：`(laughs)`（笑声）、`(chuckle)`（轻笑）、`(coughs)`（咳嗽）、`(clear-throat)`（清嗓子）、`(groans)`（呻吟）、`(breath)`（正常换气）、`(pant)`（喘气）、`(inhale)`（吸气）、`(exhale)`（呼气）、`(gasps)`（倒吸气）、`(sniffs)`（吸鼻子）、`(sighs)`（叹气）、`(snorts)`（喷鼻息）、`(burps)`（打嗝）、`(lip-smacking)`（咂嘴）、`(humming)`（哼唱）、`(hissing)`（嘶嘶声）、`(emm)`（嗯）、`(sneezes)`（喷嚏）
        stream:
          type: boolean
          description: 控制是否流式输出。默认 false，即不开启流式
        stream_options:
          $ref: '#/components/schemas/T2AStreamOption'
        voice_setting:
          $ref: '#/components/schemas/T2AVoiceSetting'
        audio_setting:
          $ref: '#/components/schemas/T2AAudioSetting'
        pronunciation_dict:
          $ref: '#/components/schemas/PronunciationDict'
        timbre_weights:
          type: array
          items:
            $ref: '#/components/schemas/TimbreWeights'
        language_boost:
          type: string
          description: |-
            是否增强对指定的小语种和方言的识别能力。默认值为 `null`，可设置为 `auto` 让模型自主判断。

            注意：speech-01 和 speech-02 系列模型暂不支持 Persian、Filipino、Tamil 这三个语种。
          enum:
            - Chinese
            - Chinese,Yue
            - English
            - Arabic
            - Russian
            - Spanish
            - French
            - Portuguese
            - German
            - Turkish
            - Dutch
            - Ukrainian
            - Vietnamese
            - Indonesian
            - Japanese
            - Italian
            - Korean
            - Thai
            - Polish
            - Romanian
            - Greek
            - Czech
            - Finnish
            - Hindi
            - Bulgarian
            - Danish
            - Hebrew
            - Malay
            - Persian
            - Slovak
            - Swedish
            - Croatian
            - Filipino
            - Hungarian
            - Norwegian
            - Slovenian
            - Catalan
            - Nynorsk
            - Tamil
            - Afrikaans
            - auto
          default: null
        voice_modify:
          $ref: '#/components/schemas/VoiceModify'
        subtitle_enable:
          type: boolean
          description: >-
            控制是否开启字幕服务，默认值为 false。仅对 `speech-2.8-hd`, `speech-2.8-turbo`,
            `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`,
            `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型有效
          default: false
        subtitle_type:
          type: string
          description: |-
            字幕粒度，默认值为 `sentence`。可选值：
            - `sentence`：句级别时间戳
            - `word`：词级别时间戳
            - `word_streaming`：流式优化的词级别时间戳，仅在 `stream=true` 时有效
          enum:
            - sentence
            - word
            - word_streaming
          default: sentence
        output_format:
          type: string
          description: >-
            控制输出结果形式的参数，可选值范围为[`url`, `hex`]，默认值为 `hex` 。该参数仅在非流式场景生效，流式场景仅支持返回
            hex 形式。返回的 url 有效期为 24 小时
          enum:
            - url
            - hex
          default: hex
        aigc_watermark:
          type: boolean
          description: 控制在合成音频的末尾添加音频节奏标识，默认值为 False。该参数仅对非流式合成生效
          default: false
    T2aV2Resp:
      type: object
      properties:
        data:
          type: object
          description: 返回的合成数据对象，可能为 null，需进行非空判断
          properties:
            audio:
              type: string
              description: 合成后的音频数据，采用 hex 编码，格式与请求中指定的输出格式一致
            subtitle_file:
              type: string
              description: 合成的字幕下载链接。音频文件对应的字幕，精确到句（不超过 50 字），单位为毫秒，格式为 json
            status:
              type: integer
              description: 当前音频流状态：1 表示合成中，2 表示合成结束
        trace_id:
          type: string
          description: 本次会话的 id，用于在咨询/反馈时帮助定位问题
        extra_info:
          type: object
          description: 音频的附加信息
          properties:
            audio_length:
              type: integer
              format: int64
              description: 音频时长（毫秒）
            audio_sample_rate:
              type: integer
              format: int64
              description: 音频采样率
            audio_size:
              type: integer
              format: int64
              description: 音频文件大小（字节）
            bitrate:
              type: integer
              format: int64
              description: 音频比特率
            audio_format:
              type: string
              description: 生成音频文件的格式。取值范围 `[mp3, pcm, flac]`
              enum:
                - mp3
                - pcm
                - flac
            audio_channel:
              type: integer
              format: int64
              description: 生成音频声道数,1：单声道，2：双声道
            invisible_character_ratio:
              type: number
              format: float64
              description: 非法字符占比.非法字符不超过 10%（包含 10%），音频会正常生成,并返回非法字符占比数据；如超过 10% 将进行报错
            usage_characters:
              type: integer
              format: int64
              description: 计费字符数
            word_count:
              type: integer
              format: int64
              description: 已发音的字数统计，包含汉字、数字、字母，不包含标点符号
        base_resp:
          type: object
          description: 本次请求的状态码和详情
          properties:
            status_code:
              type: integer
              format: int64
              description: |-
                状态码。

                 您可在header中获取本次会话的trace_id，用于在咨询/反馈时帮助定位问题 

                - `0`: 请求结果正常
                - `1000`: 未知错误
                - `1001`: 超时
                - `1002`: 触发限流
                - `1004`: 鉴权失败
                - `1039`: 触发 TPM 限流
                - `1042`: 非法字符超过 10%
                - `2013`: 输入参数信息不正常

                更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
            status_msg:
              type: string
              description: 状态详情
    T2AStreamOption:
      type: object
      properties:
        exclude_aggregated_audio:
          type: boolean
          description: >-
            设置最后一个 chunk 是否包含拼接后的语音 hex 数据。默认值为 False，即最后一个 chunk 中包含拼接后的完整语音
            hex 数据
    T2AVoiceSetting:
      type: object
      required:
        - voice_id
      properties:
        voice_id:
          type: string
          description: "合成音频的音色编号。若需要设置混合音色，请设置 timbre_weights 参数，本参数设置为空值。支持系统音色、复刻音色以及文生音色三种类型，以下是部分最新的系统音色（ID），可查看 [系统音色列表](/faq/system-voice-id) 或使用 [查询可用音色 API](/api-reference/voice-management-get) 查询系统支持的全部音色\n\n - **中文**:\n\t- moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85\n\t- moss_audio_aaa1346a-7ce7-11f0-8e61-2e6e3c7ee85d\n\t- Chinese (Mandarin)_Lyrical_Voice\n\t- Chinese (Mandarin)_HK_Flight_Attendant\n- **英文**:\n\t- English_Graceful_Lady\n\t- English_Insightful_Speaker\n\t- English_radiant_girl\n\t- English_Persuasive_Man\n\t- moss_audio_6dc281eb-713c-11f0-a447-9613c873494c\n\t- moss_audio_570551b1-735c-11f0-b236-0adeeecad052\n\t- moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8\n\t- English_Lucky_Robot\n- **日文**:\n\t- Japanese_Whisper_Belle\n\t- moss_audio_24875c4a-7be4-11f0-9359-4e72c55db738\n\t- moss_audio_7f4ee608-78ea-11f0-bb73-1e2a4cfcd245\n\t- moss_audio_c1a6a3ac-7be6-11f0-8e8e-36b92fbb4f95\n- **粤语**（需将 `language_boost` 参数设置为 `Chinese,Yue`）:\n\t- Cantonese_GentleLady\n\t- Cantonese_podacast_host_1"
        speed:
          type: number
          format: float
          description: 合成音频的语速，取值越大，语速越快。取值范围 `[0.5,2]`，默认值为1.0
          minimum: 0.5
          maximum: 2
          default: 1
        vol:
          type: number
          format: float
          description: 合成音频的音量，取值越大，音量越高。取值范围 `(0,10]`，默认值为 1.0
          exclusiveMinimum: 0
          maximum: 10
          default: 1
        pitch:
          type: integer
          description: 合成音频的语调，取值范围 `[-12,12]`，默认值为 0，其中 0 为原音色输出
          minimum: -12
          maximum: 12
          default: 0
        emotion:
          type: string
          description: "控制合成语音的情绪，参数范围 `[\"happy\", \"sad\", \"angry\", \"fearful\", \"disgusted\", \"surprised\", \"calm\", \"fluent\", \"whisper\"]`，分别对应 8 种情绪：高兴，悲伤，愤怒，害怕，厌恶，惊讶，中性，生动，低语 \r\n- 模型会根据输入文本自动匹配合适的情绪，一般无需手动指定  \r\n- 该参数仅对 `speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型生效 \r\n- 选项 `fluent`, `whisper` 仅对 `speech-2.6-turbo`, `speech-2.6-hd` 模型生效，`speech-2.8-hd`, `speech-2.8-turbo` 模型不支持 `whisper`"
          enum:
            - happy
            - sad
            - angry
            - fearful
            - disgusted
            - surprised
            - calm
            - fluent
            - whisper
        text_normalization:
          type: boolean
          description: 是否启用中文、英语文本规范化，开启后可提升数字阅读场景的性能，但会略微增加延迟，默认值为 false
          default: false
        latex_read:
          type: boolean
          description: >-
            控制是否朗读 latex 公式，默认为 false

            **需注意**:

            - 仅支持中文，开启该参数后，`language_boost` 参数会被设置为 `Chinese`

            - 请求中的公式需要在公式的首尾加上 `$$`

            - 请求中公式若有 `"\"`，需转义成 `"\\"`.


            示例：一元二次方程根的基本公式

            ![The quadratic
            formula](https://filecdn.minimax.chat/public/d6f62e9a-cd3f-4f55-a237-257eef531683.png)


            应表示为 `$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$`
          default: false
    T2AAudioSetting:
      type: object
      properties:
        sample_rate:
          type: integer
          format: int64
          description: 生成音频的采样率。可选范围`[8000，16000，22050，24000，32000，44100]`，默认为 `32000`
        bitrate:
          type: integer
          format: int64
          description: >-
            生成音频的比特率。可选范围`[32000，64000，128000，256000]`，默认值为 `128000`。该参数仅对 `mp3`
            格式的音频生效
        format:
          type: string
          description: >-
            生成音频的格式。`pcmu_raw` 与 `pcmu_wav` 为 G.711 μ-law 编码（采样率 8
            kHz；`pcmu_raw` 为无文件头裸数据，`pcmu_wav` 封装在 WAV 容器中）。`opus` 为 Ogg/Opus 编码
          enum:
            - mp3
            - pcm
            - flac
            - wav
            - pcmu_raw
            - pcmu_wav
            - opus
          default: mp3
        channel:
          type: integer
          format: int64
          description: 生成音频的声道数。可选范围：`[1,2]`，其中 `1` 为单声道，`2` 为双声道，默认值为 1
        force_cbr:
          type: boolean
          description: |-
            对于音频恒定比特率（cbr）控制，可选 `false`、 `true`。当此参数设置为 `true`，将以恒定比特率方式进行音频编码。
            注意：本参数仅当音频设置为**流式**输出，且音频格式为 `mp3` 时生效。
          default: false
    PronunciationDict:
      type: object
      properties:
        tone:
          type: array
          description: >-
            定义自定义发音规则，格式为 `原文/替换内容`。替换内容可以是纯文本、括号包裹的拼音（带声调数字）、括号包裹的 IPA
            音标，或日语假名（平假名、片假名、罗马音 —— 可混用）。多条规则会同时生效。


            示例：

            ```json dark

            "pronunciation_dict": {
              "tone": [
                "resume/(rɪˈzjuːm)",
                "read/(riːd)",
                "处理/(chu3)(li3)",
                "郑栅洁/(zheng4)(shan1)杰",
                "20日/はつか",
                "4桁/よんけた",
                "東京/トウキョウ",
                "omg/oh my god",
                "の/no"
              ]
            }

            ```


            该示例展示了：英文多音词的 IPA
            注音、中文的拼音+声调注音、拼音与汉字混合、日语假名表示数量词与汉字读音、文本到文本的展开替换、符号替换。


            中文声调：`1` = 一声，`2` = 二声，`3` = 三声，`4` = 四声，`5` = 轻声。
          items:
            type: string
    TimbreWeights:
      type: object
      required:
        - voice_id
        - weight
      properties:
        voice_id:
          type: string
          description: >-
            合成音频的音色编号，须和weight参数同步填写。支持系统音色、复刻音色以及文生音色三种类型。系统支持的全部音色可查看
            [系统音色列表](/faq/system-voice-id)，也可使用 [查询可用音色
            API](/api-reference/voice-management-get) 查询系统支持的全部音色
        weight:
          type: integer
          format: int64
          description: >-
            合成音频各音色所占的权重，须与 voice_id 同步填写。可选值范围为[1, 100]，最多支持 4
            种音色混合，单一音色取值占比越高，合成音色与该音色相似度越高.


            ```json dark

            "timbre_weights": [
              {
                "voice_id": "female-chengshu",
                "weight": 30
              },
              {
                "voice_id": "female-tianmei",
                "weight": 70
              }
            ]

            ```
          minimum: 1
          maximum: 100
    VoiceModify:
      type: object
      description: |-
        声音效果器设置，该参数支持的音频格式：
        - 非流式：`mp3`, `wav`, `flac`
        - 流式：`mp3`
      properties:
        pitch:
          type: integer
          description: >-
            音高调整（低沉/明亮），范围 [-100,100]，数值接近 -100，声音更低沉；接近 100，声音更明亮


            ![pitch
            adjustment](https://filecdn.minimax.chat/public/5d210c47-4236-4e81-893b-16cc1ef0302d.png)
          minimum: -100
          maximum: 100
        intensity:
          type: integer
          description: >-
            强度调整（力量感/柔和），范围 [-100,100]，数值接近 -100，声音更刚劲；接近 100，声音更轻柔


            ![intensity
            adjustment](https://filecdn.minimax.chat/public/862d493e-71d5-4d1f-b7c3-9ac51890631b.png)
          minimum: -100
          maximum: 100
        timbre:
          type: integer
          description: >-
            音色调整（磁性/清脆），范围 [-100,100]，数值接近 -100，声音更浑厚；数值接近 100，声音更清脆


            ![timbre
            adjustment](https://filecdn.minimax.chat/public/5f0e6cae-363a-452b-8d42-fbc4ef5a0510.png)
          minimum: -100
          maximum: 100
        sound_effects:
          type: string
          description: |-
            音效设置，单次仅能选择一种，可选值：
            1. spacious_echo（空旷回音）
            2. auditorium_echo（礼堂广播）
            3. lofi_telephone（电话失真）
            4. robotic（电音）
          enum:
            - spacious_echo
            - auditorium_echo
            - lofi_telephone
            - robotic
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 同步语音合成 WebSocket

> 使用本接口，在WebSocket网络通信协议下进行同步语音合成。



## AsyncAPI

````yaml api-reference/speech/t2a/api/asyncapi.json t2a_v2_websocket
id: t2a_v2_websocket
title: T2a_v2_websocket
description: ''
servers:
  - id: production
    protocol: wss
    host: api.minimaxi.com
    bindings: []
    variables: []
address: /ws/v1/t2a_v2
parameters: []
bindings: []
operations:
  - &ref_2
    id: sendMessage
    title: Send message
    description: ''
    type: receive
    messages:
      - &ref_4
        id: send_task_start
        contentType: application/json
        payload:
          - name: 任务开始
            description: |-
              发送`任务开始`事件则正式开始合成任务，当服务端返回的 `task_started` 事件时，标志着任务已成功开始。
              只有在接收到该事件后，才能向服务器发送 `task_continue` 事件或 `task_finish` 事件。
            type: object
            properties:
              - name: event
                type: string
                description: 控制发送的指令，当前环节应填写： `task_start`
                enumValues:
                  - task_start
                required: true
              - name: model
                type: string
                description: 请求的模型版本
                enumValues:
                  - speech-2.8-hd
                  - speech-2.8-turbo
                  - speech-2.6-hd
                  - speech-2.6-turbo
                  - speech-02-hd
                  - speech-02-turbo
                  - speech-01-hd
                  - speech-01-turbo
                required: true
              - name: voice_setting
                type: object
                required: true
                properties:
                  - name: voice_id
                    type: string
                    description: "合成音频的音色编号。若需要设置混合音色，请设置 timbre_weights 参数，本参数设置为空值。支持系统音色、复刻音色以及文生音色三种类型，以下是部分最新的系统音色（ID），可查看 [系统音色列表](/faq/system-voice-id) 或使用 [查询可用音色 API](/api-reference/voice-management-get) 查询系统支持的全部音色\n\n - **中文**:\n\t- moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85\n\t- moss_audio_aaa1346a-7ce7-11f0-8e61-2e6e3c7ee85d\n\t- Chinese (Mandarin)_Lyrical_Voice\n\t- Chinese (Mandarin)_HK_Flight_Attendant\n- **英文**:\n\t- English_Graceful_Lady\n\t- English_Insightful_Speaker\n\t- English_radiant_girl\n\t- English_Persuasive_Man\n\t- moss_audio_6dc281eb-713c-11f0-a447-9613c873494c\n\t- moss_audio_570551b1-735c-11f0-b236-0adeeecad052\n\t- moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8\n\t- English_Lucky_Robot\n- **日文**:\n\t- Japanese_Whisper_Belle\n\t- moss_audio_24875c4a-7be4-11f0-9359-4e72c55db738\n\t- moss_audio_7f4ee608-78ea-11f0-bb73-1e2a4cfcd245\n\t- moss_audio_c1a6a3ac-7be6-11f0-8e8e-36b92fbb4f95"
                    required: true
                  - name: speed
                    type: number
                    description: 合成音频的语速，取值越大，语速越快。取值范围 `[0.5,2]`，默认值为1.0
                    required: false
                  - name: vol
                    type: number
                    description: 合成音频的音量，取值越大，音量越高。取值范围 `(0,10]`，默认值为 1.0
                    required: false
                  - name: pitch
                    type: integer
                    description: 合成音频的语调，取值范围 `[-12,12]`，默认值为 0，其中 0 为原音色输出
                    required: false
                  - name: emotion
                    type: string
                    description: "控制合成语音的情绪，参数范围 `[\"happy\", \"sad\", \"angry\", \"fearful\", \"disgusted\", \"surprised\", \"calm\", \"fluent\", \"whisper\"]`，分别对应 8 种情绪：高兴，悲伤，愤怒，害怕，厌恶，惊讶，中性，生动，低语 \r\n- 模型会根据输入文本自动匹配合适的情绪，一般无需手动指定  \r\n- 该参数仅对 `speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型生效 \r\n- 选项 `fluent`, `whisper` 仅对 `speech-2.6-turbo`, `speech-2.6-hd` 模型生效，`speech-2.8-hd`, `speech-2.8-turbo` 模型不支持 `whisper`"
                    enumValues:
                      - happy
                      - sad
                      - angry
                      - fearful
                      - disgusted
                      - surprised
                      - calm
                      - fluent
                      - whisper
                    required: false
                  - name: english_normalization
                    type: boolean
                    description: 该参数支持英语文本规范化，可提升数字阅读场景的性能，但会略微增加延迟，默认值为 `false`
                    required: false
                  - name: latex_read
                    type: boolean
                    description: >-
                      控制是否朗读 latex 公式，默认为 `false`

                      **需注意**:

                      - 仅支持中文，开启该参数后，`language_boost` 参数会被设置为 `Chinese`

                      - 请求中的公式需要在公式的首尾加上 `$$`

                      - 请求中公式若有 `"\"`，需转义成 `"\\"`.


                      示例：一元二次方程根的基本公式

                      ![The quadratic
                      formula](https://filecdn.minimax.chat/public/d6f62e9a-cd3f-4f55-a237-257eef531683.png)


                      应表示为 `$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$`
                    required: false
              - name: audio_setting
                type: object
                required: false
                properties:
                  - name: sample_rate
                    type: integer
                    description: >-
                      生成音频的采样率。可选范围 `[8000，16000，22050，24000，32000，44100]`，默认为
                      `32000`
                    required: false
                  - name: bitrate
                    type: integer
                    description: >-
                      生成音频的比特率。可选范围 `[32000，64000，128000，256000]`，默认值为
                      `128000`。该参数仅对 `mp3` 格式的音频生效
                    required: false
                  - name: format
                    type: string
                    description: >-
                      生成音频的格式。`pcmu_raw` 与 `pcmu_wav` 为 G.711 μ-law 编码（采样率 8
                      kHz；`pcmu_raw` 为无文件头裸数据，`pcmu_wav` 封装在 WAV 容器中）。`opus` 为
                      Ogg/Opus 编码；流式模式下音频 chunk 需按到达顺序拼接后再解码
                    enumValues:
                      - mp3
                      - pcm
                      - flac
                      - wav
                      - pcmu_raw
                      - pcmu_wav
                      - opus
                    required: false
                  - name: channel
                    type: integer
                    description: 生成音频的声道数。可选范围：`[1,2]`，其中 `1` 为单声道，`2` 为双声道，默认值为 1
                    required: false
              - name: pronunciation_dict
                type: object
                required: false
                properties:
                  - name: tone
                    type: array
                    description: |-
                      定义需要特殊标注的文字或符号对应的注音或发音替换规则。在中文文本中，声调用数字表示：
                      一声为 1，二声为 2，三声为 3，四声为 4，轻声为 5
                      示例如下：
                      `["燕少飞/(yan4)(shao3)(fei1)", "omg/oh my god"]`
                    required: false
                    properties:
                      - name: item
                        type: string
                        required: false
              - name: timbre_weights
                type: object
                required: false
                properties:
                  - name: voice_id
                    type: string
                    description: >-
                      合成音频的音色编号，须和weight参数同步填写。支持系统音色、复刻音色以及文生音色三种类型。系统支持的全部音色可查看
                      [系统音色列表](/faq/system-voice-id)，也可使用 [查询可用音色
                      API](/api-reference/voice-management-get) 查询系统支持的全部音色
                    required: false
                  - name: weight
                    type: integer
                    description: >-
                      合成音频各音色所占的权重，须与 voice_id 同步填写。可选值范围为[1, 100]，最多支持 4
                      种音色混合，单一音色取值占比越高，合成音色与该音色相似度越高.


                      ```json dark

                      "timbre_weights": [
                        {
                          "voice_id": "female-chengshu",
                          "weight": 30
                        },
                        {
                          "voice_id": "female-tianmei",
                          "weight": 70
                        }
                      ]

                      ```
                    required: false
              - name: language_boost
                type: string
                description: >-
                  是否增强对指定的小语种和方言的识别能力，设置后可以提升在指定小语种/方言场景下的语音表现。默认值为
                  `null`，如果不明确小语种类型，可设置为 `auto`，模型将自主判断小语种类型

                  可选值范围： 

                  [`Chinese`, `Chinese,Yue`, `English`, `Arabic`, `Russian`,
                  `Spanish`, `French`, `Portuguese`, `German`, `Turkish`,
                  `Dutch`, `Ukrainian`, `Vietnamese`, `Indonesian`, `Japanese`,
                  `Italian`, `Korean`, `Thai`, `Polish`, `Romanian`, `Greek`,
                  `Czech`, `Finnish`, `Hindi`, `Bulgarian`, `Danish`, `Hebrew`,
                  `Malay`, `Persian`, `Slovak`, `Swedish`, `Croatian`,
                  `Filipino`, `Hungarian`, `Norwegian`, `Slovenian`, `Catalan`,
                  `Nynorsk`, `Tamil`, `Afrikaans`, `auto`]


                  注意：speech-01 和 speech-02 系列模型暂不支持 Persian、Filipino、Tamil
                  这三个语种。
                enumValues:
                  - Chinese
                  - Chinese,Yue
                  - English
                  - Arabic
                  - Russian
                  - Spanish
                  - French
                  - Portuguese
                  - German
                  - Turkish
                  - Dutch
                  - Ukrainian
                  - Vietnamese
                  - Indonesian
                  - Japanese
                  - Italian
                  - Korean
                  - Thai
                  - Polish
                  - Romanian
                  - Greek
                  - Czech
                  - Finnish
                  - Hindi
                  - Bulgarian
                  - Danish
                  - Hebrew
                  - Malay
                  - Persian
                  - Slovak
                  - Swedish
                  - Croatian
                  - Filipino
                  - Hungarian
                  - Norwegian
                  - Slovenian
                  - Catalan
                  - Nynorsk
                  - Tamil
                  - Afrikaans
                  - auto
                required: false
              - name: voice_modify
                type: object
                description: 声音效果器设置
                required: false
                properties:
                  - name: pitch
                    type: integer
                    description: >-
                      音高调整（低沉/明亮），范围 [-100,100]，数值接近 -100，声音更低沉；接近 100，声音更明亮


                      ![pitch
                      adjustment](https://filecdn.minimax.chat/public/5d210c47-4236-4e81-893b-16cc1ef0302d.png)
                    required: false
                  - name: intensity
                    type: integer
                    description: >-
                      强度调整（力量感/柔和），范围 [-100,100]，数值接近 -100，声音更刚劲；接近 100，声音更轻柔


                      ![intensity
                      adjustment](https://filecdn.minimax.chat/public/862d493e-71d5-4d1f-b7c3-9ac51890631b.png)
                    required: false
                  - name: timbre
                    type: integer
                    description: >-
                      音色调整（磁性/清脆），范围 [-100,100]，数值接近 -100，声音更浑厚；数值接近 100，声音更清脆


                      ![timbre
                      adjustment](https://filecdn.minimax.chat/public/5f0e6cae-363a-452b-8d42-fbc4ef5a0510.png)
                    required: false
                  - name: sound_effects
                    type: string
                    description: |-
                      音效设置，单次仅能选择一种，可选值：
                      1. spacious_echo（空旷回音）
                      2. auditorium_echo（礼堂广播）
                      3. lofi_telephone（电话失真）
                      4. robotic（电音）
                    enumValues:
                      - spacious_echo
                      - auditorium_echo
                      - lofi_telephone
                      - robotic
                    required: false
              - name: subtitle_enable
                type: boolean
                description: >-
                  控制是否开启字幕服务，默认值为 `false`。仅对 `speech-2.8-hd`,
                  `speech-2.8-turbo`, `speech-2.6-hd`, `speech-2.6-turbo`,
                  `speech-02-hd`, `speech-02-turbo`, `speech-01-hd`,
                  `speech-01-turbo` 模型有效
                required: false
              - name: subtitle_type
                type: string
                description: |-
                  字幕粒度，默认值为 `sentence`。可选值：
                  - `sentence`：句级别时间戳
                  - `word`：词级别时间戳
                  - `word_streaming`：流式优化的词级别时间戳
                enumValues:
                  - sentence
                  - word
                  - word_streaming
                required: false
              - name: continuous_sound
                type: boolean
                description: |-
                  控制模型侧文本切分策略，仅对 `speech-2.8-hd`、`speech-2.8-turbo` 模型有效。
                  - `true`：模型侧不切分文本，连续推理生成音频（长文本韵律更自然）
                  - `false`：模型侧切分文本，并发推理生成音频（延迟更低）

                  默认值为 `false`
                required: false
        headers: []
        jsonPayloadSchema:
          type: object
          required:
            - event
            - model
            - voice_setting
          properties:
            event:
              type: string
              enum:
                - task_start
              default:
                - task_start
              description: 控制发送的指令，当前环节应填写： `task_start`
              x-parser-schema-id: <anonymous-schema-6>
            model:
              type: string
              description: 请求的模型版本
              enum:
                - speech-2.8-hd
                - speech-2.8-turbo
                - speech-2.6-hd
                - speech-2.6-turbo
                - speech-02-hd
                - speech-02-turbo
                - speech-01-hd
                - speech-01-turbo
              x-parser-schema-id: <anonymous-schema-7>
            voice_setting:
              type: object
              required:
                - voice_id
              properties:
                voice_id:
                  type: string
                  description: "合成音频的音色编号。若需要设置混合音色，请设置 timbre_weights 参数，本参数设置为空值。支持系统音色、复刻音色以及文生音色三种类型，以下是部分最新的系统音色（ID），可查看 [系统音色列表](/faq/system-voice-id) 或使用 [查询可用音色 API](/api-reference/voice-management-get) 查询系统支持的全部音色\n\n - **中文**:\n\t- moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85\n\t- moss_audio_aaa1346a-7ce7-11f0-8e61-2e6e3c7ee85d\n\t- Chinese (Mandarin)_Lyrical_Voice\n\t- Chinese (Mandarin)_HK_Flight_Attendant\n- **英文**:\n\t- English_Graceful_Lady\n\t- English_Insightful_Speaker\n\t- English_radiant_girl\n\t- English_Persuasive_Man\n\t- moss_audio_6dc281eb-713c-11f0-a447-9613c873494c\n\t- moss_audio_570551b1-735c-11f0-b236-0adeeecad052\n\t- moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8\n\t- English_Lucky_Robot\n- **日文**:\n\t- Japanese_Whisper_Belle\n\t- moss_audio_24875c4a-7be4-11f0-9359-4e72c55db738\n\t- moss_audio_7f4ee608-78ea-11f0-bb73-1e2a4cfcd245\n\t- moss_audio_c1a6a3ac-7be6-11f0-8e8e-36b92fbb4f95"
                  x-parser-schema-id: <anonymous-schema-8>
                speed:
                  type: number
                  format: float
                  description: 合成音频的语速，取值越大，语速越快。取值范围 `[0.5,2]`，默认值为1.0
                  minimum: 0.5
                  maximum: 2
                  default: 1
                  x-parser-schema-id: <anonymous-schema-9>
                vol:
                  type: number
                  format: float
                  description: 合成音频的音量，取值越大，音量越高。取值范围 `(0,10]`，默认值为 1.0
                  exclusiveMinimum: 0
                  maximum: 10
                  default: 1
                  x-parser-schema-id: <anonymous-schema-10>
                pitch:
                  type: integer
                  description: 合成音频的语调，取值范围 `[-12,12]`，默认值为 0，其中 0 为原音色输出
                  minimum: -12
                  maximum: 12
                  default: 0
                  x-parser-schema-id: <anonymous-schema-11>
                emotion:
                  type: string
                  description: "控制合成语音的情绪，参数范围 `[\"happy\", \"sad\", \"angry\", \"fearful\", \"disgusted\", \"surprised\", \"calm\", \"fluent\", \"whisper\"]`，分别对应 8 种情绪：高兴，悲伤，愤怒，害怕，厌恶，惊讶，中性，生动，低语 \r\n- 模型会根据输入文本自动匹配合适的情绪，一般无需手动指定  \r\n- 该参数仅对 `speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型生效 \r\n- 选项 `fluent`, `whisper` 仅对 `speech-2.6-turbo`, `speech-2.6-hd` 模型生效，`speech-2.8-hd`, `speech-2.8-turbo` 模型不支持 `whisper`"
                  enum:
                    - happy
                    - sad
                    - angry
                    - fearful
                    - disgusted
                    - surprised
                    - calm
                    - fluent
                    - whisper
                  x-parser-schema-id: <anonymous-schema-12>
                english_normalization:
                  type: boolean
                  description: 该参数支持英语文本规范化，可提升数字阅读场景的性能，但会略微增加延迟，默认值为 `false`
                  default: false
                  x-parser-schema-id: <anonymous-schema-13>
                latex_read:
                  type: boolean
                  description: >-
                    控制是否朗读 latex 公式，默认为 `false`

                    **需注意**:

                    - 仅支持中文，开启该参数后，`language_boost` 参数会被设置为 `Chinese`

                    - 请求中的公式需要在公式的首尾加上 `$$`

                    - 请求中公式若有 `"\"`，需转义成 `"\\"`.


                    示例：一元二次方程根的基本公式

                    ![The quadratic
                    formula](https://filecdn.minimax.chat/public/d6f62e9a-cd3f-4f55-a237-257eef531683.png)


                    应表示为 `$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$`
                  default: false
                  x-parser-schema-id: <anonymous-schema-14>
              x-parser-schema-id: VoiceSetting
            audio_setting:
              type: object
              properties:
                sample_rate:
                  type: integer
                  format: int64
                  description: >-
                    生成音频的采样率。可选范围 `[8000，16000，22050，24000，32000，44100]`，默认为
                    `32000`
                  x-parser-schema-id: <anonymous-schema-15>
                bitrate:
                  type: integer
                  format: int64
                  description: >-
                    生成音频的比特率。可选范围 `[32000，64000，128000，256000]`，默认值为
                    `128000`。该参数仅对 `mp3` 格式的音频生效
                  x-parser-schema-id: <anonymous-schema-16>
                format:
                  type: string
                  description: >-
                    生成音频的格式。`pcmu_raw` 与 `pcmu_wav` 为 G.711 μ-law 编码（采样率 8
                    kHz；`pcmu_raw` 为无文件头裸数据，`pcmu_wav` 封装在 WAV 容器中）。`opus` 为
                    Ogg/Opus 编码；流式模式下音频 chunk 需按到达顺序拼接后再解码
                  enum:
                    - mp3
                    - pcm
                    - flac
                    - wav
                    - pcmu_raw
                    - pcmu_wav
                    - opus
                  default: mp3
                  x-parser-schema-id: <anonymous-schema-17>
                channel:
                  type: integer
                  format: int64
                  description: 生成音频的声道数。可选范围：`[1,2]`，其中 `1` 为单声道，`2` 为双声道，默认值为 1
                  x-parser-schema-id: <anonymous-schema-18>
              x-parser-schema-id: AudioSetting
            pronunciation_dict:
              type: object
              properties:
                tone:
                  type: array
                  items:
                    type: string
                    x-parser-schema-id: <anonymous-schema-20>
                  description: |-
                    定义需要特殊标注的文字或符号对应的注音或发音替换规则。在中文文本中，声调用数字表示：
                    一声为 1，二声为 2，三声为 3，四声为 4，轻声为 5
                    示例如下：
                    `["燕少飞/(yan4)(shao3)(fei1)", "omg/oh my god"]`
                  x-parser-schema-id: <anonymous-schema-19>
              x-parser-schema-id: PronunciationDict
            timbre_weights:
              type: object
              properties:
                voice_id:
                  type: string
                  description: >-
                    合成音频的音色编号，须和weight参数同步填写。支持系统音色、复刻音色以及文生音色三种类型。系统支持的全部音色可查看
                    [系统音色列表](/faq/system-voice-id)，也可使用 [查询可用音色
                    API](/api-reference/voice-management-get) 查询系统支持的全部音色
                  x-parser-schema-id: <anonymous-schema-21>
                weight:
                  type: integer
                  format: int64
                  description: >-
                    合成音频各音色所占的权重，须与 voice_id 同步填写。可选值范围为[1, 100]，最多支持 4
                    种音色混合，单一音色取值占比越高，合成音色与该音色相似度越高.


                    ```json dark

                    "timbre_weights": [
                      {
                        "voice_id": "female-chengshu",
                        "weight": 30
                      },
                      {
                        "voice_id": "female-tianmei",
                        "weight": 70
                      }
                    ]

                    ```
                  minimum: 1
                  maximum: 100
                  x-parser-schema-id: <anonymous-schema-22>
              x-parser-schema-id: TimbreWeights
            language_boost:
              type: string
              description: >-
                是否增强对指定的小语种和方言的识别能力，设置后可以提升在指定小语种/方言场景下的语音表现。默认值为
                `null`，如果不明确小语种类型，可设置为 `auto`，模型将自主判断小语种类型

                可选值范围： 

                [`Chinese`, `Chinese,Yue`, `English`, `Arabic`, `Russian`,
                `Spanish`, `French`, `Portuguese`, `German`, `Turkish`, `Dutch`,
                `Ukrainian`, `Vietnamese`, `Indonesian`, `Japanese`, `Italian`,
                `Korean`, `Thai`, `Polish`, `Romanian`, `Greek`, `Czech`,
                `Finnish`, `Hindi`, `Bulgarian`, `Danish`, `Hebrew`, `Malay`,
                `Persian`, `Slovak`, `Swedish`, `Croatian`, `Filipino`,
                `Hungarian`, `Norwegian`, `Slovenian`, `Catalan`, `Nynorsk`,
                `Tamil`, `Afrikaans`, `auto`]


                注意：speech-01 和 speech-02 系列模型暂不支持 Persian、Filipino、Tamil 这三个语种。
              enum:
                - Chinese
                - Chinese,Yue
                - English
                - Arabic
                - Russian
                - Spanish
                - French
                - Portuguese
                - German
                - Turkish
                - Dutch
                - Ukrainian
                - Vietnamese
                - Indonesian
                - Japanese
                - Italian
                - Korean
                - Thai
                - Polish
                - Romanian
                - Greek
                - Czech
                - Finnish
                - Hindi
                - Bulgarian
                - Danish
                - Hebrew
                - Malay
                - Persian
                - Slovak
                - Swedish
                - Croatian
                - Filipino
                - Hungarian
                - Norwegian
                - Slovenian
                - Catalan
                - Nynorsk
                - Tamil
                - Afrikaans
                - auto
              x-parser-schema-id: <anonymous-schema-23>
            voice_modify:
              type: object
              description: 声音效果器设置
              properties:
                pitch:
                  type: integer
                  description: >-
                    音高调整（低沉/明亮），范围 [-100,100]，数值接近 -100，声音更低沉；接近 100，声音更明亮


                    ![pitch
                    adjustment](https://filecdn.minimax.chat/public/5d210c47-4236-4e81-893b-16cc1ef0302d.png)
                  minimum: -100
                  maximum: 100
                  x-parser-schema-id: <anonymous-schema-24>
                intensity:
                  type: integer
                  description: >-
                    强度调整（力量感/柔和），范围 [-100,100]，数值接近 -100，声音更刚劲；接近 100，声音更轻柔


                    ![intensity
                    adjustment](https://filecdn.minimax.chat/public/862d493e-71d5-4d1f-b7c3-9ac51890631b.png)
                  minimum: -100
                  maximum: 100
                  x-parser-schema-id: <anonymous-schema-25>
                timbre:
                  type: integer
                  description: >-
                    音色调整（磁性/清脆），范围 [-100,100]，数值接近 -100，声音更浑厚；数值接近 100，声音更清脆


                    ![timbre
                    adjustment](https://filecdn.minimax.chat/public/5f0e6cae-363a-452b-8d42-fbc4ef5a0510.png)
                  minimum: -100
                  maximum: 100
                  x-parser-schema-id: <anonymous-schema-26>
                sound_effects:
                  type: string
                  description: |-
                    音效设置，单次仅能选择一种，可选值：
                    1. spacious_echo（空旷回音）
                    2. auditorium_echo（礼堂广播）
                    3. lofi_telephone（电话失真）
                    4. robotic（电音）
                  enum:
                    - spacious_echo
                    - auditorium_echo
                    - lofi_telephone
                    - robotic
                  x-parser-schema-id: <anonymous-schema-27>
              x-parser-schema-id: VoiceModify
            subtitle_enable:
              type: boolean
              description: >-
                控制是否开启字幕服务，默认值为 `false`。仅对 `speech-2.8-hd`, `speech-2.8-turbo`,
                `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`,
                `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型有效
              default: false
              x-parser-schema-id: <anonymous-schema-28>
            subtitle_type:
              type: string
              description: |-
                字幕粒度，默认值为 `sentence`。可选值：
                - `sentence`：句级别时间戳
                - `word`：词级别时间戳
                - `word_streaming`：流式优化的词级别时间戳
              enum:
                - sentence
                - word
                - word_streaming
              default: sentence
              x-parser-schema-id: <anonymous-schema-29>
            continuous_sound:
              type: boolean
              description: |-
                控制模型侧文本切分策略，仅对 `speech-2.8-hd`、`speech-2.8-turbo` 模型有效。
                - `true`：模型侧不切分文本，连续推理生成音频（长文本韵律更自然）
                - `false`：模型侧切分文本，并发推理生成音频（延迟更低）

                默认值为 `false`
              default: false
              x-parser-schema-id: <anonymous-schema-30>
          x-parser-schema-id: SendTaskStartEvent
        title: 任务开始
        description: |-
          发送`任务开始`事件则正式开始合成任务，当服务端返回的 `task_started` 事件时，标志着任务已成功开始。
          只有在接收到该事件后，才能向服务器发送 `task_continue` 事件或 `task_finish` 事件。
        example: |-
          {
            "event": "task_start",
            "model": "speech-2.8-turbo",
            "language_boost": "Chinese",
            "voice_setting": {
              "voice_id": "male-qn-qingse",
              "speed": 1,
              "vol": 1,
              "pitch": 0
            },
            "pronunciation_dict": {
              "tone": [
                "处理/(chu3)(li3)",
                "危险/dangerous"
              ]
            },
            "audio_setting": {
              "sample_rate": 32000,
              "bitrate": 128000,
              "format": "mp3",
              "channel": 1
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: send_task_start
      - &ref_5
        id: send_task_continue
        contentType: application/json
        payload:
          - name: 任务继续
            description: >-
              当收到服务端返回的 `task_started` 事件后，任务正式开始，可通过发送 `task_continue`
              事件发送要合成的文本，支持顺序发送多个 `task_continue` 事件。

              当最后一次收到服务端返回结果后超过 120s 没有发送新事件时，webSocket 连接自动断开。
            type: object
            properties:
              - name: event
                type: string
                description: 表示会话事件类型，当前环节应填写 `task_continue`
                enumValues:
                  - task_continue
                required: true
              - name: text
                type: string
                description: >-
                  需要合成语音的文本，长度限制小于 10,000 字符

                  - 段落切换用换行符标记

                  - 停顿控制：支持自定义文本之间的语音时间间隔。使用方式：在文本中增加 `<#x#>` 标记，`x`
                  为停顿时长（单位：秒），范围 **[0.01,
                  99.99]**，最多保留两位小数。文本间隔时间需设置在两个可以语音发音的文本之间，不可连续使用多个停顿标记

                  - 语气词标签：仅当模型选择 `speech-2.8-hd` 或 `speech-2.8-turbo`
                  时，支持在文本中插入语气词标签。支持的语气词：`(laughs)`（笑声）、`(chuckle)`（轻笑）、`(coughs)`（咳嗽）、`(clear-throat)`（清嗓子）、`(groans)`（呻吟）、`(breath)`（正常换气）、`(pant)`（喘气）、`(inhale)`（吸气）、`(exhale)`（呼气）、`(gasps)`（倒吸气）、`(sniffs)`（吸鼻子）、`(sighs)`（叹气）、`(snorts)`（喷鼻息）、`(burps)`（打嗝）、`(lip-smacking)`（咂嘴）、`(humming)`（哼唱）、`(hissing)`（嘶嘶声）、`(emm)`（嗯）、`(sneezes)`（喷嚏）
                required: true
        headers: []
        jsonPayloadSchema:
          type: object
          required:
            - event
            - text
          properties:
            event:
              type: string
              description: 表示会话事件类型，当前环节应填写 `task_continue`
              enum:
                - task_continue
              default:
                - task_continue
              x-parser-schema-id: <anonymous-schema-36>
            text:
              type: string
              description: >-
                需要合成语音的文本，长度限制小于 10,000 字符

                - 段落切换用换行符标记

                - 停顿控制：支持自定义文本之间的语音时间间隔。使用方式：在文本中增加 `<#x#>` 标记，`x`
                为停顿时长（单位：秒），范围 **[0.01,
                99.99]**，最多保留两位小数。文本间隔时间需设置在两个可以语音发音的文本之间，不可连续使用多个停顿标记

                - 语气词标签：仅当模型选择 `speech-2.8-hd` 或 `speech-2.8-turbo`
                时，支持在文本中插入语气词标签。支持的语气词：`(laughs)`（笑声）、`(chuckle)`（轻笑）、`(coughs)`（咳嗽）、`(clear-throat)`（清嗓子）、`(groans)`（呻吟）、`(breath)`（正常换气）、`(pant)`（喘气）、`(inhale)`（吸气）、`(exhale)`（呼气）、`(gasps)`（倒吸气）、`(sniffs)`（吸鼻子）、`(sighs)`（叹气）、`(snorts)`（喷鼻息）、`(burps)`（打嗝）、`(lip-smacking)`（咂嘴）、`(humming)`（哼唱）、`(hissing)`（嘶嘶声）、`(emm)`（嗯）、`(sneezes)`（喷嚏）
              x-parser-schema-id: <anonymous-schema-37>
          x-parser-schema-id: SendTaskContinueEvent
        title: 任务继续
        description: >-
          当收到服务端返回的 `task_started` 事件后，任务正式开始，可通过发送 `task_continue`
          事件发送要合成的文本，支持顺序发送多个 `task_continue` 事件。

          当最后一次收到服务端返回结果后超过 120s 没有发送新事件时，webSocket 连接自动断开。
        example: |-
          {
            "event": "task_continue",
            "text": "真正的危险不是计算机开始像人一样思考(sighs)，而是人开始像计算机一样思考。计算机只是可以帮我们处理一些简单事务。"
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: send_task_continue
      - &ref_6
        id: send_task_finish
        contentType: application/json
        payload:
          - name: 任务结束
            description: 服务端收到 `task_finish` 事件后，会等待当前队列中所有合成任务完成后，关闭 WebSocket 连接并结束任务。
            type: object
            properties:
              - name: event
                type: string
                description: 表示会话事件类型，当前环节应填写 `task_finish`
                enumValues:
                  - task_finish
                required: true
        headers: []
        jsonPayloadSchema:
          type: object
          required:
            - event
          properties:
            event:
              type: string
              enum:
                - task_finish
              default:
                - task_finish
              description: 表示会话事件类型，当前环节应填写 `task_finish`
              x-parser-schema-id: <anonymous-schema-55>
          x-parser-schema-id: SendTaskFinishEvent
        title: 任务结束
        description: 服务端收到 `task_finish` 事件后，会等待当前队列中所有合成任务完成后，关闭 WebSocket 连接并结束任务。
        example: |-
          {
            "event": "task_finish"
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: send_task_finish
    bindings: []
    extensions: &ref_1
      - id: x-parser-unique-object-id
        value: t2a_v2_websocket
  - &ref_3
    id: receiveMessage
    title: Receive message
    type: send
    messages:
      - &ref_7
        id: receive_connected_success
        contentType: application/json
        payload:
          - name: 建连成功
            description: 成功建立连接后会返回 `connected_success` 事件
            type: object
            properties:
              - name: session_id
                type: string
                description: 表示整个会话的 id
                required: false
              - name: event
                type: string
                description: 表示会话事件类型，建连成功后会返回`connected_success`
                required: false
              - name: trace_id
                type: string
                description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
                required: false
              - name: base_resp
                type: object
                required: false
                properties:
                  - name: status_code
                    type: integer
                    description: |-
                      状态码，`0`代表建连成功.
                      更多状态码信息请参考 [错误码查询列表](/api-reference/errorcode)
                    required: false
                  - name: status_msg
                    type: string
                    description: 该请求对应的状态码和详情
                    required: false
        headers: []
        jsonPayloadSchema:
          type: object
          properties:
            session_id:
              type: string
              description: 表示整个会话的 id
              x-parser-schema-id: <anonymous-schema-1>
            event:
              type: string
              const: connected_success
              description: 表示会话事件类型，建连成功后会返回`connected_success`
              x-parser-schema-id: <anonymous-schema-2>
            trace_id:
              type: string
              description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
              x-parser-schema-id: <anonymous-schema-3>
            base_resp:
              type: object
              properties:
                status_code:
                  type: integer
                  description: |-
                    状态码，`0`代表建连成功.
                    更多状态码信息请参考 [错误码查询列表](/api-reference/errorcode)
                  x-parser-schema-id: <anonymous-schema-4>
                status_msg:
                  type: string
                  description: 该请求对应的状态码和详情
                  x-parser-schema-id: <anonymous-schema-5>
              x-parser-schema-id: BaseResp
          x-parser-schema-id: ReceiveConnectedSuccessEvent
        title: 建连成功
        description: 成功建立连接后会返回 `connected_success` 事件
        example: |-
          {
            "session_id": "xxxx",
            "event": "connected_success",
            "trace_id": "0303a2882bf18235ae7a809ae0f3cca7",
            "base_resp": {
              "status_code": 0,
              "status_msg": "success"
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: receive_connected_success
      - &ref_8
        id: receive_task_started
        contentType: application/json
        payload:
          - name: 任务开始
            description: 服务端返回 `task_started` 事件，标志着任务已成功开始
            type: object
            properties:
              - name: session_id
                type: string
                description: 表示整个会话的 id
                required: false
              - name: event
                type: string
                description: 表示会话事件类型，当前环节成功后会返回 `task_started`
                required: false
              - name: trace_id
                type: string
                description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
                required: false
              - name: base_resp
                type: object
                description: 该请求对应的状态码和详情
                required: false
                properties:
                  - name: status_code
                    type: integer
                    description: |-
                      状态码。
                      - 0: 表示发送成功
                      - 2202: 表示非法事件
                      更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                    required: false
                  - name: status_msg
                    type: string
                    description: 状态详情
                    required: false
        headers: []
        jsonPayloadSchema:
          type: object
          properties:
            session_id:
              type: string
              description: 表示整个会话的 id
              x-parser-schema-id: <anonymous-schema-31>
            event:
              type: string
              const: 表示会话事件类型，当前环节成功后会返回 `task_started`
              x-parser-schema-id: <anonymous-schema-32>
            trace_id:
              type: string
              description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
              x-parser-schema-id: <anonymous-schema-33>
            base_resp: &ref_0
              type: object
              description: 该请求对应的状态码和详情
              properties:
                status_code:
                  type: integer
                  description: |-
                    状态码。
                    - 0: 表示发送成功
                    - 2202: 表示非法事件
                    更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                  x-parser-schema-id: <anonymous-schema-34>
                status_msg:
                  type: string
                  description: 状态详情
                  x-parser-schema-id: <anonymous-schema-35>
              x-parser-schema-id: TaskStartFinishBaseResp
          x-parser-schema-id: ReceiveTaskStartedEvent
        title: 任务开始
        description: 服务端返回 `task_started` 事件，标志着任务已成功开始
        example: |-
          {
            "session_id": "xxxx",
            "event": "task_started",
            "trace_id": "0303a2882bf18235ae7a809ae0f3cca7",
            "base_resp": {
              "status_code": 0,
              "status_msg": "success"
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: receive_task_started
      - &ref_9
        id: receive_task_continued
        contentType: application/json
        payload:
          - name: 任务继续
            description: 服务端返回 `task_continued` 事件，标志着任务已成功继续
            type: object
            properties:
              - name: data
                type: object
                description: '`data` 可能返回为 `null`，参考示例代码时，注意进行非空判断'
                required: false
                properties:
                  - name: audio
                    type: string
                    description: 合成后的音频片段，采用 `hex` 编码，按照输入定义的格式进行生成（mp3/pcm/flac）
                    required: false
              - name: trace_id
                type: string
                description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题。
                required: false
              - name: session_id
                type: string
                description: 表示整个会话的 id。
                required: false
              - name: event
                type: string
                description: 表示会话类型，当前环节成功后会返回 task_continued`
                required: false
              - name: is_final
                type: boolean
                description: 该请求返回是否完结
                required: false
              - name: extra_info
                type: object
                description: 相关额外信息
                required: false
                properties:
                  - name: audio_length
                    type: integer
                    description: 音频时长，精确到毫秒
                    required: false
                  - name: audio_sample_rate
                    type: integer
                    description: 音频采样率
                    required: false
                  - name: audio_size
                    type: integer
                    description: 音频文件大小，单位为字节
                    required: false
                  - name: bitrate
                    type: integer
                    description: 音频比特率
                    required: false
                  - name: audio_format
                    type: string
                    description: 生成音频文件的格式。取值范围 mp3/pcm/flac
                    required: false
                  - name: audio_channel
                    type: integer
                    description: 生成音频声道数。1：单声道，2：双声道
                    required: false
                  - name: invisible_character_ratio
                    type: integer
                    description: 非法字符占比。非法字符不超过 10%（包含 10%），音频会正常生成并返回非法字符占比，超过进行报错
                    required: false
                  - name: usage_characters
                    type: integer
                    description: 计费字符数。本次语音生成的计费字符数
                    required: false
                  - name: word_count
                    type: integer
                    description: 已发音的字数统计，包含汉字、数字、字母，不包含标点符号
                    required: false
              - name: base_resp
                type: object
                description: 本次请求的状态码和详情
                required: false
                properties:
                  - name: status_code
                    type: integer
                    description: |-
                      状态码
                      - 0: 请求结果正常
                      - 1000: 未知错误
                      - 1001: 请求超时
                      - 1002: 触发限流
                      - 1004: 鉴权失败
                      - 1039: 触发 TPM 限流
                      - 1042: 非法字符超过 10%
                      - 2013: 输入参数信息不正常
                      - 2201: 超时断开连接
                      - 2202: 非法事件
                      - 2203: 空文本，跳过
                      - 2204: 超出字符限制，跳过
                      - 2205: 请求超限
                      更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                    required: false
                  - name: status_msg
                    type: string
                    description: 状态详情
                    required: false
        headers: []
        jsonPayloadSchema:
          type: object
          properties:
            data:
              type: object
              description: '`data` 可能返回为 `null`，参考示例代码时，注意进行非空判断'
              properties:
                audio:
                  type: string
                  description: 合成后的音频片段，采用 `hex` 编码，按照输入定义的格式进行生成（mp3/pcm/flac）
                  x-parser-schema-id: <anonymous-schema-39>
              x-parser-schema-id: <anonymous-schema-38>
            trace_id:
              type: string
              description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题。
              x-parser-schema-id: <anonymous-schema-40>
            session_id:
              type: string
              description: 表示整个会话的 id。
              x-parser-schema-id: <anonymous-schema-41>
            event:
              type: string
              description: 表示会话类型，当前环节成功后会返回 task_continued`
              x-parser-schema-id: <anonymous-schema-42>
            is_final:
              type: boolean
              description: 该请求返回是否完结
              x-parser-schema-id: <anonymous-schema-43>
            extra_info:
              type: object
              description: 相关额外信息
              properties:
                audio_length:
                  type: integer
                  format: int64
                  description: 音频时长，精确到毫秒
                  x-parser-schema-id: <anonymous-schema-44>
                audio_sample_rate:
                  type: integer
                  format: int64
                  description: 音频采样率
                  x-parser-schema-id: <anonymous-schema-45>
                audio_size:
                  type: integer
                  format: int64
                  description: 音频文件大小，单位为字节
                  x-parser-schema-id: <anonymous-schema-46>
                bitrate:
                  type: integer
                  format: int64
                  description: 音频比特率
                  x-parser-schema-id: <anonymous-schema-47>
                audio_format:
                  type: string
                  description: 生成音频文件的格式。取值范围 mp3/pcm/flac
                  x-parser-schema-id: <anonymous-schema-48>
                audio_channel:
                  type: integer
                  format: int64
                  description: 生成音频声道数。1：单声道，2：双声道
                  x-parser-schema-id: <anonymous-schema-49>
                invisible_character_ratio:
                  type: integer
                  format: float
                  description: 非法字符占比。非法字符不超过 10%（包含 10%），音频会正常生成并返回非法字符占比，超过进行报错
                  x-parser-schema-id: <anonymous-schema-50>
                usage_characters:
                  type: integer
                  format: int64
                  description: 计费字符数。本次语音生成的计费字符数
                  x-parser-schema-id: <anonymous-schema-51>
                word_count:
                  type: integer
                  format: int64
                  description: 已发音的字数统计，包含汉字、数字、字母，不包含标点符号
                  x-parser-schema-id: <anonymous-schema-52>
              x-parser-schema-id: ExtraInfo
            base_resp:
              type: object
              description: 本次请求的状态码和详情
              properties:
                status_code:
                  type: integer
                  description: |-
                    状态码
                    - 0: 请求结果正常
                    - 1000: 未知错误
                    - 1001: 请求超时
                    - 1002: 触发限流
                    - 1004: 鉴权失败
                    - 1039: 触发 TPM 限流
                    - 1042: 非法字符超过 10%
                    - 2013: 输入参数信息不正常
                    - 2201: 超时断开连接
                    - 2202: 非法事件
                    - 2203: 空文本，跳过
                    - 2204: 超出字符限制，跳过
                    - 2205: 请求超限
                    更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                  x-parser-schema-id: <anonymous-schema-53>
                status_msg:
                  type: string
                  description: 状态详情
                  x-parser-schema-id: <anonymous-schema-54>
              x-parser-schema-id: TaskContinueBaseResp
          x-parser-schema-id: ReceiveTaskContinuedEvent
        title: 任务继续
        description: 服务端返回 `task_continued` 事件，标志着任务已成功继续
        example: |-
          {
            "data": {
              "audio": "xxx"
            },
            "extra_info": {
              "audio_channel": 1,
              "audio_format": "mp3",
              "audio_length": 9914,
              "audio_sample_rate": 32000,
              "audio_size": 157869,
              "bitrate": 128000,
              "invisible_character_ratio": 0,
              "usage_characters": 158,
              "word_count": 158
            },
            "is_final": true,
            "session_id": "301871346491491",
            "trace_id": "04ee3794e2c9e4a6d5f99e77742f06fd",
            "base_resp": {
              "status_code": 0,
              "status_msg": "success"
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: receive_task_continued
      - &ref_10
        id: receive_task_finished
        contentType: application/json
        payload:
          - name: 任务结束
            description: 服务端返回 `task_finished` 事件，标志着任务已成功结束
            type: object
            properties:
              - name: trace_id
                type: string
                description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
                required: false
              - name: session_id
                type: string
                description: 表示整个会话的 id
                required: false
              - name: event
                type: string
                description: 表示会话类型，当前环节成功后会返回 `task_finished`
                required: false
              - name: base_resp
                type: object
                description: 该请求对应的状态码和详情
                required: false
                properties:
                  - name: status_code
                    type: integer
                    description: |-
                      状态码。
                      - 0: 表示发送成功
                      - 2202: 表示非法事件
                      更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                    required: false
                  - name: status_msg
                    type: string
                    description: 状态详情
                    required: false
        headers: []
        jsonPayloadSchema:
          type: object
          properties:
            trace_id:
              type: string
              description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
              x-parser-schema-id: <anonymous-schema-56>
            session_id:
              type: string
              description: 表示整个会话的 id
              x-parser-schema-id: <anonymous-schema-57>
            event:
              type: string
              description: 表示会话类型，当前环节成功后会返回 `task_finished`
              x-parser-schema-id: <anonymous-schema-58>
            base_resp: *ref_0
          x-parser-schema-id: ReceiveTaskFinishedEvent
        title: 任务结束
        description: 服务端返回 `task_finished` 事件，标志着任务已成功结束
        example: |-
          {
            "session_id": "xxxx",
            "event": "task_finished",
            "trace_id": "0303a2882bf18235ae7a809ae0f3cca7",
            "base_resp": {
              "status_code": 0,
              "status_msg": "success"
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: receive_task_finished
      - &ref_11
        id: receive_task_failed
        contentType: application/json
        payload:
          - name: 任务失败
            description: 如果接收到 `task_failed` 事件，表示任务失败。此时需要关闭 WebSocket 连接并处理错误。
            type: object
            properties:
              - name: trace_id
                type: string
                description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
                required: false
              - name: session_id
                type: string
                description: 表示整个会话的 id
                required: false
              - name: event
                type: string
                description: 表示会话类型，任务失败会返回 `task_failed`
                required: false
              - name: base_resp
                type: object
                description: 本次请求的状态码和详情
                required: false
                properties:
                  - name: status_code
                    type: integer
                    description: |-
                      状态码
                      - `1000`: 未知错误
                      - `1001`: 超时
                      - `1002`: 触发限流
                      - `1004`: 鉴权失败
                      - `1039`: 触发 TPM 限流
                      - `1042`: 非法字符超过 10%
                      - `2013`: 输入参数信息不正常
                      - `2201`: 超时断开连接
                      更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                    required: false
                  - name: status_msg
                    type: string
                    description: 状态详情
                    required: false
        headers: []
        jsonPayloadSchema:
          type: object
          properties:
            trace_id:
              type: string
              description: 表示会话中单次请求的 id，用于在咨询/反馈时帮助定位问题
              x-parser-schema-id: <anonymous-schema-59>
            session_id:
              type: string
              description: 表示整个会话的 id
              x-parser-schema-id: <anonymous-schema-60>
            event:
              type: string
              description: 表示会话类型，任务失败会返回 `task_failed`
              x-parser-schema-id: <anonymous-schema-61>
            base_resp:
              type: object
              description: 本次请求的状态码和详情
              properties:
                status_code:
                  type: integer
                  description: |-
                    状态码
                    - `1000`: 未知错误
                    - `1001`: 超时
                    - `1002`: 触发限流
                    - `1004`: 鉴权失败
                    - `1039`: 触发 TPM 限流
                    - `1042`: 非法字符超过 10%
                    - `2013`: 输入参数信息不正常
                    - `2201`: 超时断开连接
                    更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
                  x-parser-schema-id: <anonymous-schema-62>
                status_msg:
                  type: string
                  description: 状态详情
                  x-parser-schema-id: <anonymous-schema-63>
              x-parser-schema-id: TaskFailedBaseResp
          x-parser-schema-id: ReceiveTaskFailedEvent
        title: 任务失败
        description: 如果接收到 `task_failed` 事件，表示任务失败。此时需要关闭 WebSocket 连接并处理错误。
        example: |-
          {
            "session_id": "xxxx",
            "event": "task_failed",
            "trace_id": "0303a2882bf18235ae7a809ae0f3cca7",
            "base_resp": {
              "status_code": 1004,
              "status_msg": "XXXXXXX"
            }
          }
        bindings: []
        extensions:
          - id: x-parser-unique-object-id
            value: receive_task_failed
    bindings: []
    extensions: *ref_1
sendOperations:
  - *ref_2
receiveOperations:
  - *ref_3
sendMessages:
  - *ref_4
  - *ref_5
  - *ref_6
receiveMessages:
  - *ref_7
  - *ref_8
  - *ref_9
  - *ref_10
  - *ref_11
extensions:
  - id: x-parser-unique-object-id
    value: t2a_v2_websocket
securitySchemes: []

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 创建异步语音合成任务

> 使用本接口，创建异步语音合成任务。

### 返回文件信息

#### txt 文件

输出文件如下所示

* 音频文件：文件格式遵从请求体设置
* 字幕文件：精确到句的字幕信息
* 额外信息 JSON 文件：音频文件相关的附加信息

#### json 文件

* `title`，若该字段为空，则不输出该字段的文件
  * 音频文件：文件格式遵从请求体设置
  * 字幕文件：精确到句的字幕信息
  * 额外信息 JSON 文件：音频文件相关的附加信息

* `content`，若该字段为空，则不输出该字段的文件
  * 音频文件：文件格式遵从请求体设置
  * 字幕文件：精确到句的字幕信息
  * 额外信息 JSON 文件：音频文件相关的附加信息

* `extra`，若该字段为空，则不输出该字段的文件
  * 音频文件：文件格式遵从请求体设置
  * 字幕文件：精确到句的字幕信息
  * 额外信息 JSON 文件：音频文件相关的附加信息


## OpenAPI

````yaml api-reference/speech/t2a-async/api/openapi.json POST /v1/t2a_async_v2
openapi: 3.1.0
info:
  title: MiniMax T2A Async API
  description: >-
    MiniMax Text-to-Audio Async API with support for long text processing and
    task querying
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/t2a_async_v2:
    post:
      tags:
        - Text to Audio
      summary: Text to Audio Async V2
      operationId: t2aAsyncV2
      parameters:
        - name: Content-Type
          in: header
          required: true
          description: 请求体的媒介类型，请设置为 `application/json`，确保请求数据的格式为 JSON
          schema:
            type: string
            enum:
              - application/json
            default: application/json
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/T2AAsyncV2Req'
            examples:
              文本输入:
                value:
                  model: speech-2.8-hd
                  text: 真正的危险不是计算机开始像人一样思考(sighs)，而是人开始像计算机一样思考。计算机只是可以帮我们处理一些简单事务。
                  language_boost: auto
                  voice_setting:
                    voice_id: audiobook_male_1
                    speed: 1
                    vol: 1
                    pitch: 1
                  pronunciation_dict:
                    tone:
                      - 危险/dangerous
                  audio_setting:
                    audio_sample_rate: 32000
                    bitrate: 128000
                    format: mp3
                    channel: 2
                  voice_modify:
                    pitch: 0
                    intensity: 0
                    timbre: 0
                    sound_effects: spacious_echo
              文件输入:
                value:
                  model: speech-2.8-hd
                  text_file_id: text_file_id
                  language_boost: auto
                  voice_setting:
                    voice_id: audiobook_male_1
                    speed: 1
                    vol: 10
                    pitch: 1
                  pronunciation_dict:
                    tone:
                      - 草地/(cao3)(di1)
                  audio_setting:
                    audio_sample_rate: 32000
                    bitrate: 128000
                    format: mp3
                    channel: 2
                  voice_modify:
                    pitch: 0
                    intensity: 0
                    timbre: 0
                    sound_effects: spacious_echo
        required: true
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/T2AAsyncV2Resp'
              examples:
                文本输入:
                  value:
                    task_id: 95157322514444
                    task_token: eyJhbGciOiJSUz
                    file_id: 95157322514444
                    usage_characters: 101
                    base_resp:
                      status_code: 0
                      status_msg: success
                文件输入:
                  value:
                    task_id: 95157322514444
                    task_token: eyJhbGciOiJSUz
                    file_id: 95157322514444
                    usage_characters: 101
                    base_resp:
                      status_code: 0
                      status_msg: success
components:
  schemas:
    T2AAsyncV2Req:
      type: object
      required:
        - model
        - text
        - text_file_id
        - voice_setting
      properties:
        model:
          type: string
          description: >-
            请求的模型版本，可选范围：`speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`,
            `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`,
            `speech-01-hd`, `speech-01-turbo`.
          enum:
            - speech-2.8-hd
            - speech-2.8-turbo
            - speech-2.6-hd
            - speech-2.6-turbo
            - speech-02-hd
            - speech-02-turbo
            - speech-01-hd
            - speech-01-turbo
        text:
          type: string
          description: >-
            待合成音频的文本，限制最长 5 万字符。和 `text_file_id` 二选一必填

            - 语气词标签：仅当模型选择 `speech-2.8-hd` 或 `speech-2.8-turbo`
            时，支持在文本中插入语气词标签。支持的语气词：`(laughs)`（笑声）、`(chuckle)`（轻笑）、`(coughs)`（咳嗽）、`(clear-throat)`（清嗓子）、`(groans)`（呻吟）、`(breath)`（正常换气）、`(pant)`（喘气）、`(inhale)`（吸气）、`(exhale)`（呼气）、`(gasps)`（倒吸气）、`(sniffs)`（吸鼻子）、`(sighs)`（叹气）、`(snorts)`（喷鼻息）、`(burps)`（打嗝）、`(lip-smacking)`（咂嘴）、`(humming)`（哼唱）、`(hissing)`（嘶嘶声）、`(emm)`（嗯）、`(whistles)`（口哨）、`(sneezes)`（喷嚏）、`(crying)`（抽泣）、`(applause)`（鼓掌）
        text_file_id:
          type: integer
          format: int64
          description: "待合成音频的文本文件 待合成音频的文本文件 id，单个文件长度限制小于 100 万字符，支持的文件格式：txt、zip。和 `text` 二选一必填，传入后自动校验格式。\n- **txt 文件**：长度限制 <1,000,000 字符。支持使用 <#x#> 标记自定义停顿。x 为停顿时长（单位：秒），范围 [0.01,99.99]，最多保留两位小数。注意停顿需设置在两个可以语音发音的文本之间，不可连续使用多个停顿标记\n- **zip 文件**：\n\t- 压缩包内需包含同一格式的 txt 或 json 文件。\n\t- json 文件格式：支持 [`title`, `content`, `extra`] 三个字段，分别表示标题、正文、附加信息。若三个字段都存在，则产出 3 组结果，共 9 个文件，统一存放在一个文件夹中。若某字段不存在或内容为空，则该字段不会生成对应结果"
        voice_setting:
          $ref: '#/components/schemas/T2AAsyncV2VoiceSetting'
        audio_setting:
          $ref: '#/components/schemas/T2AAsyncV2AudioSetting'
        pronunciation_dict:
          $ref: '#/components/schemas/T2AAsyncV2PronunciationDict'
        language_boost:
          type: string
          description: |-
            是否增强对指定的小语种和方言的识别能力。默认值为 `null`，可设置为 `auto` 让模型自主判断。

            注意：speech-01 和 speech-02 系列模型暂不支持 Persian、Filipino、Tamil 这三个语种。
          enum:
            - Chinese
            - Chinese,Yue
            - English
            - Arabic
            - Russian
            - Spanish
            - French
            - Portuguese
            - German
            - Turkish
            - Dutch
            - Ukrainian
            - Vietnamese
            - Indonesian
            - Japanese
            - Italian
            - Korean
            - Thai
            - Polish
            - Romanian
            - Greek
            - Czech
            - Finnish
            - Hindi
            - Bulgarian
            - Danish
            - Hebrew
            - Malay
            - Persian
            - Slovak
            - Swedish
            - Croatian
            - Filipino
            - Hungarian
            - Norwegian
            - Slovenian
            - Catalan
            - Nynorsk
            - Tamil
            - Afrikaans
            - auto
          default: null
        voice_modify:
          $ref: '#/components/schemas/VoiceModify'
        aigc_watermark:
          type: boolean
          description: 控制在合成音频的末尾添加音频节奏标识，默认值为 False。该参数仅对非流式合成生效
          default: false
    T2AAsyncV2Resp:
      type: object
      properties:
        task_id:
          type: string
          description: 当前任务的 ID
        file_id:
          type: integer
          format: int64
          description: >-
            任务创建成功后返回的对应音频文件的 ID。

            - 当任务完成后，可通过 file_id 调用
            [文件检索接口](/api-reference/file-management-retrieve) 进行下载

            - 当请求出错时，不返回该字段

            注意：返回的下载 URL 自生成起 9 小时（32,400 秒）内有效，过期后文件将失效，生成的信息便会丢失，请注意下载信息的时间
        task_token:
          type: string
          description: 完成当前任务使用的密钥信息
        usage_characters:
          type: integer
          description: 计费字符数
        base_resp:
          $ref: '#/components/schemas/BaseResp'
    T2AAsyncV2VoiceSetting:
      type: object
      required:
        - voice_id
      properties:
        voice_id:
          type: string
          description: "合成音频的音色编号。若需要设置混合音色，请设置 timbre_weights 参数，本参数设置为空值。支持系统音色、复刻音色以及文生音色三种类型，以下是部分最新的系统音色（ID），可查看 [系统音色列表](/faq/system-voice-id) 或使用 [查询可用音色 API](/api-reference/voice-management-get) 查询系统支持的全部音色\n\n - **中文**:\n\t- moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85\n\t- moss_audio_aaa1346a-7ce7-11f0-8e61-2e6e3c7ee85d\n\t- Chinese (Mandarin)_Lyrical_Voice\n\t- Chinese (Mandarin)_HK_Flight_Attendant\n- **英文**:\n\t- English_Graceful_Lady\n\t- English_Insightful_Speaker\n\t- English_radiant_girl\n\t- English_Persuasive_Man\n\t- moss_audio_6dc281eb-713c-11f0-a447-9613c873494c\n\t- moss_audio_570551b1-735c-11f0-b236-0adeeecad052\n\t- moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8\n\t- English_Lucky_Robot\n- **日文**:\n\t- Japanese_Whisper_Belle\n\t- moss_audio_24875c4a-7be4-11f0-9359-4e72c55db738\n\t- moss_audio_7f4ee608-78ea-11f0-bb73-1e2a4cfcd245\n\t- moss_audio_c1a6a3ac-7be6-11f0-8e8e-36b92fbb4f95"
        speed:
          type: number
          format: float
          description: 合成音频的语速，取值越大，语速越快。取值范围 `[0.5,2]`，默认值为1.0
          minimum: 0.5
          maximum: 2
          default: 1
        vol:
          type: number
          format: float
          description: 合成音频的音量，取值越大，音量越高。取值范围 `(0,10]`，默认值为 1.0
          exclusiveMinimum: 0
          maximum: 10
          default: 1
        pitch:
          type: integer
          description: 合成音频的语调，取值范围 `[-12,12]`，默认值为 0，其中 0 为原音色输出
          minimum: -12
          maximum: 12
          default: 0
        emotion:
          type: string
          description: "控制合成语音的情绪，参数范围 `[\"happy\", \"sad\", \"angry\", \"fearful\", \"disgusted\", \"surprised\", \"calm\", \"fluent\", \"whisper\"]`，分别对应 8 种情绪：高兴，悲伤，愤怒，害怕，厌恶，惊讶，中性，生动，低语 \r\n- 模型会根据输入文本自动匹配合适的情绪，一般无需手动指定  \r\n- 该参数仅对 `speech-2.8-hd`, `speech-2.8-turbo`, `speech-2.6-hd`, `speech-2.6-turbo`, `speech-02-hd`, `speech-02-turbo`, `speech-01-hd`, `speech-01-turbo` 模型生效 \r\n- 选项 `fluent`, `whisper` 仅对 `speech-2.6-turbo`, `speech-2.6-hd` 模型生效，`speech-2.8-hd`, `speech-2.8-turbo` 模型不支持 `whisper`"
          enum:
            - happy
            - sad
            - angry
            - fearful
            - disgusted
            - surprised
            - calm
            - fluent
            - whisper
        english_normalization:
          type: boolean
          description: 支持英语文本规范化，开启后可提升数字阅读场景的性能，但会略微增加延迟，默认 false
          default: false
    T2AAsyncV2AudioSetting:
      type: object
      properties:
        audio_sample_rate:
          type: integer
          format: int64
          default: 32000
          description: >-
            生成音频的采样率。可选范围 `[8000，16000，22050，24000，32000，44100]`，默认为 `32000`。

            注意：当输出格式为 `opus` 时，仅支持 `[8000, 12000, 16000, 24000,
            48000]`，使用其他采样率会导致任务报错。
        bitrate:
          type: integer
          format: int64
          default: 128000
          description: >-
            生成音频的比特率。可选范围 `[32000，64000，128000，256000]`，默认值为 `128000`。该参数仅对
            `mp3` 格式的音频生效
        format:
          type: string
          description: >-
            生成音频的格式。可选范围 `[mp3, pcm, flac, wav, pcmu_raw, pcmu_wav, opus]`，默认值为
            `mp3`。`pcmu_raw` 与 `pcmu_wav` 为 G.711 μ-law 编码（采样率 8 kHz；`pcmu_raw`
            为无文件头裸数据，`pcmu_wav` 封装在 WAV 容器中）。`opus` 为 Ogg/Opus 编码，仅支持采样率 `[8000,
            12000, 16000, 24000, 48000]`，使用其他采样率会导致任务报错。
          enum:
            - mp3
            - pcm
            - flac
            - wav
            - pcmu_raw
            - pcmu_wav
            - opus
          default: mp3
        channel:
          type: integer
          format: int64
          default: 2
          description: 生成音频的声道数。可选范围：`[1,2]`，其中 `1` 为单声道，`2` 为双声道，默认值为 2
    T2AAsyncV2PronunciationDict:
      type: object
      properties:
        tone:
          type: array
          description: |-
            定义需要特殊标注的文字或符号对应的注音或发音替换规则。在中文文本中，声调用数字表示：
            一声为 1，二声为 2，三声为 3，四声为 4，轻声为 5
            示例如下：
            `["燕少飞/(yan4)(shao3)(fei1)", "omg/oh my god"]`
          items:
            type: string
    VoiceModify:
      type: object
      description: >-
        声音效果器设置。


        支持的音频格式：`mp3`、`wav`、`flac`。（其他格式如 `pcm`、`pcmu_raw`、`pcmu_wav`、`opus`
        不支持，传入会返回参数错误。）
      properties:
        pitch:
          type: integer
          description: >-
            音高调整（低沉/明亮），范围 [-100,100]，数值接近 -100，声音更低沉；接近 100，声音更明亮


            ![pitch
            adjustment](https://filecdn.minimax.chat/public/5d210c47-4236-4e81-893b-16cc1ef0302d.png)
          minimum: -100
          maximum: 100
        intensity:
          type: integer
          description: >-
            强度调整（力量感/柔和），范围 [-100,100]，数值接近 -100，声音更刚劲；接近 100，声音更轻柔


            ![intensity
            adjustment](https://filecdn.minimax.chat/public/862d493e-71d5-4d1f-b7c3-9ac51890631b.png)
          minimum: -100
          maximum: 100
        timbre:
          type: integer
          description: >-
            音色调整（磁性/清脆），范围 [-100,100]，数值接近 -100，声音更浑厚；数值接近 100，声音更清脆


            ![timbre
            adjustment](https://filecdn.minimax.chat/public/5f0e6cae-363a-452b-8d42-fbc4ef5a0510.png)
          minimum: -100
          maximum: 100
        sound_effects:
          type: string
          description: |-
            音效设置，单次仅能选择一种，可选值：
            1. spacious_echo（空旷回音）
            2. auditorium_echo（礼堂广播）
            3. lofi_telephone（电话失真）
            4. robotic（电音）
          enum:
            - spacious_echo
            - auditorium_echo
            - lofi_telephone
            - robotic
    BaseResp:
      type: object
      description: 本次请求的状态码及其详情
      required:
        - status_code
        - status_msg
      properties:
        status_code:
          type: integer
          format: int64
          description: |-
            状态码

            - `0`: 正常
            - `1002`: 限流
            - `1004`: 鉴权失败
            - `1039`: 触发 TPM 限流
            - `1042`: 非法字符超10%
            - `2013`: 参数错误

            更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
        status_msg:
          type: string
          description: 状态详情
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 查询语音生成任务状态

> 使用本接口，查询异步语音合成任务状态。

**注：该 API 限制每秒最多查询 10 次。**


## OpenAPI

````yaml api-reference/speech/t2a-async/api/openapi.json GET /v1/query/t2a_async_query_v2
openapi: 3.1.0
info:
  title: MiniMax T2A Async API
  description: >-
    MiniMax Text-to-Audio Async API with support for long text processing and
    task querying
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/query/t2a_async_query_v2:
    get:
      tags:
        - Text to Audio
      summary: Query T2A Async V2 Task Status
      operationId: t2aAsyncV2Query
      parameters:
        - name: task_id
          in: query
          required: true
          description: 任务 ID，提交任务时返回的信息
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/T2AAsyncV2QueryResp'
components:
  schemas:
    T2AAsyncV2QueryResp:
      type: object
      properties:
        task_id:
          type: integer
          format: int64
          description: 任务 ID
        status:
          type: string
          description: |-
            该任务的当前状态。

            - **Processing**: 该任务正在处理中
            - **Success**: 该任务已完成
            - **Failed**: 任务失败
            - **Expired**: 任务已过期
          enum:
            - success
            - failed
            - expired
            - processing
        file_id:
          type: integer
          format: int64
          description: >-
            任务创建成功后返回的对应音频文件的 ID。

            - 当任务完成后，可通过 file_id 调用
            [文件检索接口](/api-reference/file-management-retrieve) 进行下载

            - 当请求出错时，不返回该字段

            注意：返回的下载 URL 自生成起 9 小时（32,400 秒）内有效，过期后文件将失效，生成的信息便会丢失，请注意下载信息的时间
        base_resp:
          $ref: '#/components/schemas/BaseResp'
      example:
        task_id: 95157322514444
        status: Processing
        file_id: 95157322514496
        base_resp:
          status_code: 0
          status_msg: success
    BaseResp:
      type: object
      description: 本次请求的状态码及其详情
      required:
        - status_code
        - status_msg
      properties:
        status_code:
          type: integer
          format: int64
          description: |-
            状态码

            - `0`: 正常
            - `1002`: 限流
            - `1004`: 鉴权失败
            - `1039`: 触发 TPM 限流
            - `1042`: 非法字符超10%
            - `2013`: 参数错误

            更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
        status_msg:
          type: string
          description: 状态详情
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 查询语音生成任务状态

> 使用本接口，查询异步语音合成任务状态。

**注：该 API 限制每秒最多查询 10 次。**


## OpenAPI

````yaml api-reference/speech/t2a-async/api/openapi.json GET /v1/query/t2a_async_query_v2
openapi: 3.1.0
info:
  title: MiniMax T2A Async API
  description: >-
    MiniMax Text-to-Audio Async API with support for long text processing and
    task querying
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/query/t2a_async_query_v2:
    get:
      tags:
        - Text to Audio
      summary: Query T2A Async V2 Task Status
      operationId: t2aAsyncV2Query
      parameters:
        - name: task_id
          in: query
          required: true
          description: 任务 ID，提交任务时返回的信息
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/T2AAsyncV2QueryResp'
components:
  schemas:
    T2AAsyncV2QueryResp:
      type: object
      properties:
        task_id:
          type: integer
          format: int64
          description: 任务 ID
        status:
          type: string
          description: |-
            该任务的当前状态。

            - **Processing**: 该任务正在处理中
            - **Success**: 该任务已完成
            - **Failed**: 任务失败
            - **Expired**: 任务已过期
          enum:
            - success
            - failed
            - expired
            - processing
        file_id:
          type: integer
          format: int64
          description: >-
            任务创建成功后返回的对应音频文件的 ID。

            - 当任务完成后，可通过 file_id 调用
            [文件检索接口](/api-reference/file-management-retrieve) 进行下载

            - 当请求出错时，不返回该字段

            注意：返回的下载 URL 自生成起 9 小时（32,400 秒）内有效，过期后文件将失效，生成的信息便会丢失，请注意下载信息的时间
        base_resp:
          $ref: '#/components/schemas/BaseResp'
      example:
        task_id: 95157322514444
        status: Processing
        file_id: 95157322514496
        base_resp:
          status_code: 0
          status_msg: success
    BaseResp:
      type: object
      description: 本次请求的状态码及其详情
      required:
        - status_code
        - status_msg
      properties:
        status_code:
          type: integer
          format: int64
          description: |-
            状态码

            - `0`: 正常
            - `1002`: 限流
            - `1004`: 鉴权失败
            - `1039`: 触发 TPM 限流
            - `1042`: 非法字符超10%
            - `2013`: 参数错误

            更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
        status_msg:
          type: string
          description: 状态详情
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 上传示例音频

> 使用本接口上传示例音频文件，使用示例音频将有助于增强语音合成的音色相似度和稳定性。



## OpenAPI

````yaml api-reference/speech/voice-cloning/api/upload-prompt.json POST /v1/files/upload
openapi: 3.1.0
info:
  title: MiniMax Voice Cloning API
  description: MiniMax Voice Cloning API with support for voice cloning and file upload
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/files/upload:
    post:
      tags:
        - Files
      summary: Upload File
      operationId: uploadFile
      parameters:
        - name: Content-Type
          in: header
          required: true
          description: '请求体的媒介类型 `multipart/form-data` '
          schema:
            type: string
            enum:
              - multipart/form-data
            default: multipart/form-datan
      requestBody:
        description: ''
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - purpose
                - file
              properties:
                purpose:
                  type: string
                  description: |-
                    文件使用目的。取值及支持格式如下：
                    - __prompt_audio__: 快速复刻原始文件，（支持mp3、m4a、wav格式）
                  default: prompt_audio
                  enum:
                    - prompt_audio
                  example: prompt_audio
                file:
                  type: string
                  format: binary
                  description: |-
                    需要上传的文件。填写文件的路径地址 

                    支持上传的文件需遵从以下规范：
                    - 上传的音频文件格式需为：mp3、m4a、wav格式
                    - 上传的音频文件的时长小于8s
                    - 上传的音频文件大小需不超过20mb
        required: true
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UploadFileResp'
components:
  schemas:
    UploadFileResp:
      type: object
      properties:
        file:
          $ref: '#/components/schemas/FileObject'
        base_resp:
          $ref: '#/components/schemas/UploadFileBaseResp'
      example:
        file:
          file_id: ${file_id}
          bytes: 5896337
          created_at: 1700469398
          filename: sample.mp3
          purpose: prompt_audio
        base_resp:
          status_code: 0
          status_msg: success
    FileObject:
      type: object
      properties:
        file_id:
          type: integer
          format: int64
          description: 文件的唯一标识符
        bytes:
          type: integer
          format: int64
          description: 文件大小，以字节为单位
        created_at:
          type: integer
          format: int64
          description: 创建文件时的 Unix 时间戳，以秒为单位
        filename:
          type: string
          description: 文件的名称
        purpose:
          type: string
          description: 文件的使用目的
          default:
            - prompt_audio
    UploadFileBaseResp:
      type: object
      properties:
        status_code:
          type: integer
          description: |-
            状态码及其分别含义如下：
            - 0，请求成功
            - 1002，触发限流，请稍后再试
            - 1004，账号鉴权失败，请检查 API-Key 是否填写正确
            - 1008，账号余额不足
            - 1026，图片描述涉及敏感内容
            - 2013，传入参数异常，请检查入参是否按要求填写
            - 2049，无效的api key

            更多内容可查看错误码查询列表了解详情
        status_msg:
          type: string
          description: 状态详情
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 音色快速复刻

> 使用本接口进行音色快速复刻。
复刻得到的音色若 7 天内未正式调用，则系统会删除该音色。
调用本接口前，请先完成个人或企业认证。



## OpenAPI

````yaml api-reference/speech/voice-cloning/api/openapi.json POST /v1/voice_clone
openapi: 3.1.0
info:
  title: MiniMax Voice Cloning API
  description: MiniMax Voice Cloning API with support for voice cloning and file upload
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/voice_clone:
    post:
      tags:
        - Voice
      summary: Voice Clone
      operationId: voiceClone
      requestBody:
        description: Voice clone request parameters
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/VoiceCloneReq'
        required: true
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/VoiceCloneResp'
components:
  schemas:
    VoiceCloneReq:
      type: object
      required:
        - file_id
        - voice_id
      properties:
        file_id:
          type: integer
          format: int64
          description: |-
            待复刻音频的 file_id，通过[文件上传接口](/api-reference/file-management-upload)获得
            上传的待复刻音频文件需遵从以下规范：

            - 上传的音频文件格式需为：mp3、m4a、wav 格式
            - 上传的音频文件的时长最少应不低于 10 秒，最长应不超过 5 分钟
            - 上传的音频文件大小需不超过 20 mb
            - 若使用该参数，则两个子属性（prompt_audio、prompt_text）都为必填项
        voice_id:
          type: string
          description: |-
            克隆音色的 voice_id，正确示例："MiniMax001"。用户进行自定义 voice_id 时需注意：

            - 自定义的 voice_id 长度范围[8,256]
            - 首字符必须为英文字母
            - 允许数字、字母、-、_
            - 末位字符不可为 -、_
            - voice_id 不可与已有 id 重复，否则会报错
        clone_prompt:
          $ref: '#/components/schemas/ClonePrompt'
          description: |-
            音色复刻示例音频，提供本参数将有助于增强语音合成的音色相似度和稳定性。若使用本参数，需同时上传一小段示例音频
            上传的音频文件需遵从以下规范：

            - 上传的音频文件格式需为：mp3、m4a、wav 格式
            - 上传的音频文件的时长小于 8 秒
            - 上传的音频文件大小需不超过 20 mb
        text:
          type: string
          description: >-
            复刻试听参数，限制 1000 字符以内。模型将使用复刻后的音色朗读本段文本内容，并返回试听音频链接。
             注：试听将根据字符数正常收取语音合成费用，定价与 T2A 各接口一致
            - 语气词标签：仅当模型选择 `speech-2.8-hd` 或 `speech-2.8-turbo`
            时，支持在文本中插入语气词标签。支持的语气词：`(laughs)`（笑声）、`(chuckle)`（轻笑）、`(coughs)`（咳嗽）、`(clear-throat)`（清嗓子）、`(groans)`（呻吟）、`(breath)`（正常换气）、`(pant)`（喘气）、`(inhale)`（吸气）、`(exhale)`（呼气）、`(gasps)`（倒吸气）、`(sniffs)`（吸鼻子）、`(sighs)`（叹气）、`(snorts)`（喷鼻息）、`(burps)`（打嗝）、`(lip-smacking)`（咂嘴）、`(humming)`（哼唱）、`(hissing)`（嘶嘶声）、`(emm)`（嗯）、`(whistles)`（口哨）、`(sneezes)`（喷嚏）、`(crying)`（抽泣）、`(applause)`（鼓掌）
        model:
          type: string
          description: 复刻试听参数。指定合成试听音频使用的语音模型，提供 `text` 字段时必传此字段。可选项：
          enum:
            - speech-2.8-hd
            - speech-2.8-turbo
            - speech-2.6-hd
            - speech-2.6-turbo
            - speech-02-hd
            - speech-02-turbo
            - speech-01-hd
            - speech-01-turbo
        language_boost:
          type: string
          description: 是否增强对指定的小语种和方言的识别能力。默认值为 null，可设置为 `auto` 让模型自主判断。
          enum:
            - Chinese
            - Chinese,Yue
            - English
            - Arabic
            - Russian
            - Spanish
            - French
            - Portuguese
            - German
            - Turkish
            - Dutch
            - Ukrainian
            - Vietnamese
            - Indonesian
            - Japanese
            - Italian
            - Korean
            - Thai
            - Polish
            - Romanian
            - Greek
            - Czech
            - Finnish
            - Hindi
            - Bulgarian
            - Danish
            - Hebrew
            - Malay
            - Persian
            - Slovak
            - Swedish
            - Croatian
            - Filipino
            - Hungarian
            - Norwegian
            - Slovenian
            - Catalan
            - Nynorsk
            - Tamil
            - Afrikaans
            - auto
        text_validation:
          type: string
          description: >-
            可选参数。音频复刻样本（`file_id` 或 `clone_prompt.prompt_audio`
            中的音频）的预期文本内容。提供后，服务会对该音频做 ASR 识别，并将识别文本与 `text_validation`
            做相似度比对；若相似度低于 `accuracy`，请求会被拒绝并返回错误码 `1043`（`The asr similarity
            check failed`）。长度上限 200 字符。
          maxLength: 200
        accuracy:
          type: number
          format: double
          description: >-
            可选参数。配合 `text_validation` 使用的 ASR 相似度阈值，取值范围 `[0, 1]`。未传或传 `0` 时取默认值
            `0.7`。
          minimum: 0
          maximum: 1
          default: 0.7
        need_noise_reduction:
          type: boolean
          description: 音频复刻参数，表示是否开启降噪，默认值为 false
          default: false
        need_volume_normalization:
          type: boolean
          description: 音频复刻参数，是否开启音量归一化，默认值为 false
          default: false
        aigc_watermark:
          type: boolean
          description: 是否在合成试听音频的末尾添加音频节奏标识，默认值为 false
          default: false
      example:
        file_id: 123456789
        voice_id: <voice_id>
        clone_prompt:
          prompt_audio: 987654321
          prompt_text: This voice sounds natural and pleasant.
        text: >-
          A gentle breeze sweeps across the soft grass(breath), carrying the
          fresh scent along with the songs of birds.
        model: speech-2.8-hd
        text_validation: This voice sounds natural and pleasant.
        accuracy: 0.7
        need_noise_reduction: false
        need_volume_normalization: false
        aigc_watermark: false
    VoiceCloneResp:
      type: object
      properties:
        input_sensitive:
          type: object
          description: 输入音频是否命中风控
          properties:
            type:
              type: integer
              description: |-
                输入音频命中风控的类型，取值为以下其一：

                - 0：正常
                - 1：严重违规
                - 2：色情
                - 3：广告
                - 4：违禁
                - 5：谩骂
                - 6：暴恐
                - 7：其他
        demo_audio:
          type: string
          description: 如果请求体中传入了试听文本 text 以及合成试听音频的模型 model，那么本参数将以链接形式返回试听音频，否则本参数为空值
        extra_info:
          type: object
          description: 试听音频的元信息和计费信息。仅当请求中带 `text`（即触发了试听合成、有计费）时返回。字段结构与 `/v1/t2a_v2` 对齐
          properties:
            audio_length:
              type: integer
              format: int64
              description: 试听音频时长（毫秒）
            audio_sample_rate:
              type: integer
              format: int64
              description: 试听音频采样率
            audio_size:
              type: integer
              format: int64
              description: 试听音频文件大小（字节）
            bitrate:
              type: integer
              format: int64
              description: 试听音频比特率
            word_count:
              type: integer
              format: int64
              description: 已发音的字数统计，包含汉字、数字、字母，不包含标点符号
            usage_characters:
              type: integer
              format: int64
              description: 本次试听合成的计费字符数，可用于和账单进行对账
        base_resp:
          $ref: '#/components/schemas/VoiceCloneBaseResponse'
      example:
        input_sensitive: false
        input_sensitive_type: 0
        demo_audio: ''
        extra_info:
          audio_length: 11124
          audio_sample_rate: 32000
          audio_size: 179926
          bitrate: 128000
          word_count: 18
          usage_characters: 18
        base_resp:
          status_code: 0
          status_msg: success
    ClonePrompt:
      type: object
      properties:
        prompt_audio:
          type: integer
          format: int64
          description: 示例音频的 file_id，通过 [文件上传接口](/api-reference/file-management-upload) 获得
        prompt_text:
          type: string
          description: 示例音频的对应文本，需确保和音频内容一致，句末需有标点符号做结尾
    VoiceCloneBaseResponse:
      type: object
      required:
        - status_code
      properties:
        status_code:
          type: integer
          format: int64
          description: |-
            状态码

            - 0: 请求结果正常
            - 1000：未知错误
            - 1001：超时
            - 1002：触发限流
            - 1004：鉴权失败
            - 1013：服务内部错误
            - 2013：输入格式信息不正常
            - 2038：无复刻权限，请检查账号认证状态

            更多内容可查看[错误码查询列表](/api-reference/errorcode)了解详情
        status_msg:
          type: string
          description: 状态详情
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 音色设计

> 使用本接口，输入文本内容，进行音色设计。



## OpenAPI

````yaml api-reference/speech/voice-design/api/openapi.json POST /v1/voice_design
openapi: 3.1.0
info:
  title: MiniMax Voice Design API
  description: MiniMax Voice Design API with support for voice generation from text prompts
  license:
    name: MIT
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/voice_design:
    post:
      tags:
        - Voice
      summary: Voice Design
      operationId: voiceDesign
      parameters:
        - name: Content-Type
          in: header
          required: true
          description: 请求体的媒介类型，请设置为 `application/json`，确保请求数据的格式为 JSON
          schema:
            type: string
            enum:
              - application/json
            default: application/json
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/T2VReq'
        required: true
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/T2VResp'
components:
  schemas:
    T2VReq:
      type: object
      required:
        - prompt
        - preview_text
      properties:
        prompt:
          type: string
          description: 音色描述。
        preview_text:
          type: string
          description: |-
            试听音频文本。
            注：试听音频的合成将收取 2 元/万字符的费用
          maxLength: 500
        voice_id:
          type: string
          description: 自定义生成音色的 voice_id。当不传入此参数时，将自动生成并返回一个唯一的 `voice_id`
        aigc_watermark:
          type: boolean
          description: 是否在合成试听音频的末尾添加音频节奏标识，默认值为 False
      example:
        prompt: 讲述悬疑故事的播音员，声音低沉富有磁性，语速时快时慢，营造紧张神秘的氛围。
        preview_text: 夜深了，古屋里只有他一人。窗外传来若有若无的脚步声，他屏住呼吸，慢慢地，慢慢地，走向那扇吱呀作响的门……
    T2VResp:
      type: object
      properties:
        voice_id:
          type: string
          description: 生成的音色 ID，可用于语音合成
        trial_audio:
          type: string
          description: 使用生成的音色合成的试听音频，以 hex 编码形式返回
        base_resp:
          type: object
          description: 状态码和状态详情
          properties:
            status_code:
              type: integer
              format: int64
              description: |-
                状态码。

                - `0`: 请求结果正常
                - `1000`: 未知错误
                - `1001`: 超时
                - `1002`: 触发 RPM 限流
                - `1004`: 鉴权失败
                - `1008`: 余额不足
                - `1013`: 服务内部错误
                - `1027`: 输出内容错误
                - `1039`: 触发 TPM 限流
                - `2013`: 输入格式信息不正常

                更多内容可查看 [错误码查询列表](/api-reference/errorcode) 了解详情
            status_msg:
              type: string
              description: 状态详情
      example:
        trial_audio: hex 编码音频
        voice_id: ttv-voice-2025060717322425-xxxxxxxx
        base_resp:
          status_code: 0
          status_msg: success
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 获取模型列表

> 获取平台支持的所有模型列表，兼容 OpenAI API 规范



## OpenAPI

````yaml api-reference/models/openai/api/list-models.json GET /v1/models
openapi: 3.1.0
info:
  title: MiniMax Models API
  description: MiniMax models API compatible with OpenAI API specification.
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/models:
    get:
      tags:
        - Models
      summary: 获取模型列表
      description: 获取平台支持的所有模型列表。该接口兼容 OpenAI API 规范。
      operationId: listModels
      responses:
        '200':
          description: 可用模型列表。
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                    description: 对象类型，固定为 `"list"`
                  data:
                    type: array
                    description: 模型对象数组
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: 模型标识符
                        object:
                          type: string
                          description: 对象类型，固定为 `"model"`
                        created:
                          type: integer
                          description: 模型创建时间（Unix 时间戳）
                        owned_by:
                          type: string
                          description: 模型所属组织
              examples:
                默认响应:
                  value:
                    object: list
                    data:
                      - id: MiniMax-M3
                        object: model
                        created: 1780272000
                        owned_by: minimax
                      - id: MiniMax-M2.7
                        object: model
                        created: 1773799200
                        owned_by: minimax
                      - id: MiniMax-M2.5
                        object: model
                        created: 1770948000
                        owned_by: minimax
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 获取模型列表

> 获取平台支持的所有模型列表，兼容 OpenAI API 规范



## OpenAPI

````yaml api-reference/models/openai/api/list-models.json GET /v1/models
openapi: 3.1.0
info:
  title: MiniMax Models API
  description: MiniMax models API compatible with OpenAI API specification.
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/models:
    get:
      tags:
        - Models
      summary: 获取模型列表
      description: 获取平台支持的所有模型列表。该接口兼容 OpenAI API 规范。
      operationId: listModels
      responses:
        '200':
          description: 可用模型列表。
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                    description: 对象类型，固定为 `"list"`
                  data:
                    type: array
                    description: 模型对象数组
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: 模型标识符
                        object:
                          type: string
                          description: 对象类型，固定为 `"model"`
                        created:
                          type: integer
                          description: 模型创建时间（Unix 时间戳）
                        owned_by:
                          type: string
                          description: 模型所属组织
              examples:
                默认响应:
                  value:
                    object: list
                    data:
                      - id: MiniMax-M3
                        object: model
                        created: 1780272000
                        owned_by: minimax
                      - id: MiniMax-M2.7
                        object: model
                        created: 1773799200
                        owned_by: minimax
                      - id: MiniMax-M2.5
                        object: model
                        created: 1770948000
                        owned_by: minimax
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 获取模型列表

> 获取平台支持的所有模型列表，兼容 OpenAI API 规范



## OpenAPI

````yaml api-reference/models/openai/api/list-models.json GET /v1/models
openapi: 3.1.0
info:
  title: MiniMax Models API
  description: MiniMax models API compatible with OpenAI API specification.
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - bearerAuth: []
paths:
  /v1/models:
    get:
      tags:
        - Models
      summary: 获取模型列表
      description: 获取平台支持的所有模型列表。该接口兼容 OpenAI API 规范。
      operationId: listModels
      responses:
        '200':
          description: 可用模型列表。
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                    description: 对象类型，固定为 `"list"`
                  data:
                    type: array
                    description: 模型对象数组
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: 模型标识符
                        object:
                          type: string
                          description: 对象类型，固定为 `"model"`
                        created:
                          type: integer
                          description: 模型创建时间（Unix 时间戳）
                        owned_by:
                          type: string
                          description: 模型所属组织
              examples:
                默认响应:
                  value:
                    object: list
                    data:
                      - id: MiniMax-M3
                        object: model
                        created: 1780272000
                        owned_by: minimax
                      - id: MiniMax-M2.7
                        object: model
                        created: 1773799200
                        owned_by: minimax
                      - id: MiniMax-M2.5
                        object: model
                        created: 1770948000
                        owned_by: minimax
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |-
        `HTTP: Bearer Auth`
         - Security Scheme Type: http
         - HTTP Authorization Scheme: Bearer API_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看

````

> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 获取单个模型详情

> 获取指定模型的详细信息，兼容 Anthropic API 规范。



## OpenAPI

````yaml api-reference/models/anthropic/api/retrieve-model.json GET /anthropic/v1/models/{model_id}
openapi: 3.1.0
info:
  title: MiniMax Models API
  description: MiniMax models API compatible with Anthropic API specification.
  version: 1.0.0
servers:
  - url: https://api.minimaxi.com
security:
  - apiKeyAuth: []
paths:
  /anthropic/v1/models/{model_id}:
    get:
      tags:
        - Models
      summary: 获取单个模型详情
      description: 获取指定模型的详细信息。
      operationId: anthropicRetrieveModel
      parameters:
        - name: model_id
          in: path
          required: true
          description: 模型标识符
          schema:
            type: string
      responses:
        '200':
          description: 指定模型的详细信息。
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    description: 模型标识符
                  created_at:
                    type: string
                    description: 模型创建时间（ISO 8601 格式）
                  display_name:
                    type: string
                    description: 模型显示名称
                  type:
                    type: string
                    description: 模型类型，固定为 `"model"`
              examples:
                默认响应:
                  value:
                    id: MiniMax-M3
                    created_at: '2026-06-01T00:00:00Z'
                    display_name: MiniMax-M3
                    type: model
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-Api-Key
      description: |-
        `API Key Auth`
         - Security Scheme Type: apiKey
         - API Key Header: X-Api-Key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看

````

