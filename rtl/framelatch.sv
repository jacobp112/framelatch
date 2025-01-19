`timescale 1ns/1ps
`default_nettype none

module framelatch (
    input  wire         clk,
    input  wire         rst,
    input  wire [7:0]   in_data,
    input  wire         in_valid,
    output wire         in_ready,
    input  wire         in_abort,
    output reg  [127:0] out_payload,
    output reg  [4:0]   out_length,
    output reg          out_valid,
    input  wire         out_ready,
    output reg  [31:0]  valid_frames,
    output reg  [31:0]  crc_errors,
    output reg  [31:0]  invalid_lengths,
    output reg  [31:0]  incomplete_frames,
    output reg  [31:0]  discarded_bytes
);
    localparam [1:0] SEARCH = 2'd0, LENGTH = 2'd1,
                     PAYLOAD = 2'd2, CRC = 2'd3;
    reg [1:0] state;
    reg [4:0] frame_length;
    reg [3:0] payload_index;
    reg [127:0] assembly;
    reg [7:0] crc_acc;

    function automatic [7:0] crc_byte(input [7:0] crc, input [7:0] data);
        reg [7:0] value;
        integer bit_index;
        begin
            value = crc ^ data;
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                value = value[7] ? (value << 1) ^ 8'h07 : (value << 1);
            crc_byte = value;
        end
    endfunction

    function automatic [31:0] saturate(input [31:0] value);
        saturate = (&value) ? value : value + 32'd1;
    endfunction

    // A pending stalled output freezes input, including sync-search bytes.
    // Abort suppresses input transfer even when the parser is idle.
    assign in_ready = !rst && !in_abort && (!out_valid || out_ready);

    always @(posedge clk) begin
        if (rst) begin
            state <= SEARCH;
            frame_length <= 0;
            payload_index <= 0;
            assembly <= 0;
            crc_acc <= 0;
            out_payload <= 0;
            out_length <= 0;
            out_valid <= 0;
            valid_frames <= 0;
            crc_errors <= 0;
            invalid_lengths <= 0;
            incomplete_frames <= 0;
            discarded_bytes <= 0;
        end else begin
            if (out_valid && out_ready)
                out_valid <= 0;

            if (in_abort) begin
                if (state != SEARCH)
                    incomplete_frames <= saturate(incomplete_frames);
                state <= SEARCH;
                frame_length <= 0;
                payload_index <= 0;
                assembly <= 0;
                crc_acc <= 0;
            end else if (in_valid && in_ready) begin
                case (state)
                    SEARCH: begin
                        if (in_data == 8'hA5) begin
                            state <= LENGTH;
                            assembly <= 0;
                            crc_acc <= 0;
                            payload_index <= 0;
                        end else
                            discarded_bytes <= saturate(discarded_bytes);
                    end
                    LENGTH: begin
                        if (in_data == 0 || in_data > 16) begin
                            invalid_lengths <= saturate(invalid_lengths);
                            state <= SEARCH;
                        end else begin
                            frame_length <= in_data[4:0];
                            crc_acc <= crc_byte(8'h00, in_data);
                            state <= PAYLOAD;
                        end
                    end
                    PAYLOAD: begin
                        assembly[payload_index * 8 +: 8] <= in_data;
                        crc_acc <= crc_byte(crc_acc, in_data);
                        if ({1'b0, payload_index} == frame_length - 5'd1)
                            state <= CRC;
                        else
                            payload_index <= payload_index + 4'd1;
                    end
                    CRC: begin
                        state <= SEARCH;
                        if (in_data == crc_acc) begin
                            out_payload <= assembly;
                            out_length <= frame_length;
                            out_valid <= 1;
                            valid_frames <= saturate(valid_frames);
                        end else
                            crc_errors <= saturate(crc_errors);
                    end
                    default: state <= SEARCH;
                endcase
            end
        end
    end
endmodule

`default_nettype wire
