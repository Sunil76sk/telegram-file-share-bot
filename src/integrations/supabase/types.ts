export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      bot_config: {
        Row: {
          admin_telegram_ids: number[]
          backup_join_channel_id: number | null
          backup_join_channel_username: string | null
          backup_storage_chat_id: number | null
          bot_username: string | null
          id: number
          main_channel_id: number | null
          main_channel_username: string | null
          shortener_api_key: string | null
          storage_chat_id: number | null
          updated_at: string
        }
        Insert: {
          admin_telegram_ids?: number[]
          backup_join_channel_id?: number | null
          backup_join_channel_username?: string | null
          backup_storage_chat_id?: number | null
          bot_username?: string | null
          id?: number
          main_channel_id?: number | null
          main_channel_username?: string | null
          shortener_api_key?: string | null
          storage_chat_id?: number | null
          updated_at?: string
        }
        Update: {
          admin_telegram_ids?: number[]
          backup_join_channel_id?: number | null
          backup_join_channel_username?: string | null
          backup_storage_chat_id?: number | null
          bot_username?: string | null
          id?: number
          main_channel_id?: number | null
          main_channel_username?: string | null
          shortener_api_key?: string | null
          storage_chat_id?: number | null
          updated_at?: string
        }
        Relationships: []
      }
      channel_posts: {
        Row: {
          auto_repost_hours: number | null
          buttons: Json
          caption: string
          created_at: string
          created_by: string | null
          error: string | null
          id: string
          image_link_url: string | null
          last_sent_at: string | null
          photo_url: string | null
          scheduled_at: string | null
          status: string
          telegram_message_id: number | null
          updated_at: string
        }
        Insert: {
          auto_repost_hours?: number | null
          buttons?: Json
          caption: string
          created_at?: string
          created_by?: string | null
          error?: string | null
          id?: string
          image_link_url?: string | null
          last_sent_at?: string | null
          photo_url?: string | null
          scheduled_at?: string | null
          status?: string
          telegram_message_id?: number | null
          updated_at?: string
        }
        Update: {
          auto_repost_hours?: number | null
          buttons?: Json
          caption?: string
          created_at?: string
          created_by?: string | null
          error?: string | null
          id?: string
          image_link_url?: string | null
          last_sent_at?: string | null
          photo_url?: string | null
          scheduled_at?: string | null
          status?: string
          telegram_message_id?: number | null
          updated_at?: string
        }
        Relationships: []
      }
      downloads: {
        Row: {
          created_at: string
          id: string
          movie_id: string
          source: string | null
          telegram_user_id: number
        }
        Insert: {
          created_at?: string
          id?: string
          movie_id: string
          source?: string | null
          telegram_user_id: number
        }
        Update: {
          created_at?: string
          id?: string
          movie_id?: string
          source?: string | null
          telegram_user_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "downloads_movie_id_fkey"
            columns: ["movie_id"]
            isOneToOne: false
            referencedRelation: "movies"
            referencedColumns: ["id"]
          },
        ]
      }
      movie_views: {
        Row: {
          created_at: string
          id: string
          movie_id: string
          source: string | null
          telegram_user_id: number
        }
        Insert: {
          created_at?: string
          id?: string
          movie_id: string
          source?: string | null
          telegram_user_id: number
        }
        Update: {
          created_at?: string
          id?: string
          movie_id?: string
          source?: string | null
          telegram_user_id?: number
        }
        Relationships: [
          {
            foreignKeyName: "movie_views_movie_id_fkey"
            columns: ["movie_id"]
            isOneToOne: false
            referencedRelation: "movies"
            referencedColumns: ["id"]
          },
        ]
      }
      movies: {
        Row: {
          backup_message_id: number | null
          content_type: string
          created_at: string
          created_by_telegram_id: number | null
          deep_link: string | null
          file_size: number | null
          file_unique_id: string | null
          genre: string | null
          id: string
          language: string | null
          movie_file_id: string | null
          poster_file_id: string | null
          rating: number | null
          short_url: string | null
          shortener_last_error: string | null
          shortener_status: string
          shortener_url: string | null
          storage_chat_id: number | null
          storage_message_id: number | null
          title: string
          updated_at: string
          year: number | null
        }
        Insert: {
          backup_message_id?: number | null
          content_type?: string
          created_at?: string
          created_by_telegram_id?: number | null
          deep_link?: string | null
          file_size?: number | null
          file_unique_id?: string | null
          genre?: string | null
          id?: string
          language?: string | null
          movie_file_id?: string | null
          poster_file_id?: string | null
          rating?: number | null
          short_url?: string | null
          shortener_last_error?: string | null
          shortener_status?: string
          shortener_url?: string | null
          storage_chat_id?: number | null
          storage_message_id?: number | null
          title: string
          updated_at?: string
          year?: number | null
        }
        Update: {
          backup_message_id?: number | null
          content_type?: string
          created_at?: string
          created_by_telegram_id?: number | null
          deep_link?: string | null
          file_size?: number | null
          file_unique_id?: string | null
          genre?: string | null
          id?: string
          language?: string | null
          movie_file_id?: string | null
          poster_file_id?: string | null
          rating?: number | null
          short_url?: string | null
          shortener_last_error?: string | null
          shortener_status?: string
          shortener_url?: string | null
          storage_chat_id?: number | null
          storage_message_id?: number | null
          title?: string
          updated_at?: string
          year?: number | null
        }
        Relationships: []
      }
      profiles: {
        Row: {
          first_name: string | null
          id: string
          joined_at: string
          last_seen_at: string
          telegram_user_id: number
          username: string | null
        }
        Insert: {
          first_name?: string | null
          id?: string
          joined_at?: string
          last_seen_at?: string
          telegram_user_id: number
          username?: string | null
        }
        Update: {
          first_name?: string | null
          id?: string
          joined_at?: string
          last_seen_at?: string
          telegram_user_id?: number
          username?: string | null
        }
        Relationships: []
      }
      scheduled_deletions: {
        Row: {
          chat_id: number
          created_at: string
          delete_at: string
          id: number
          message_id: number
        }
        Insert: {
          chat_id: number
          created_at?: string
          delete_at: string
          id?: number
          message_id: number
        }
        Update: {
          chat_id?: number
          created_at?: string
          delete_at?: string
          id?: number
          message_id?: number
        }
        Relationships: []
      }
      series_episodes: {
        Row: {
          created_at: string
          episode_number: number
          file_id: string
          file_size: number | null
          file_unique_id: string
          id: string
          movie_id: string
          season_number: number
          storage_chat_id: number
          storage_message_id: number
          title: string | null
        }
        Insert: {
          created_at?: string
          episode_number: number
          file_id: string
          file_size?: number | null
          file_unique_id: string
          id?: string
          movie_id: string
          season_number: number
          storage_chat_id: number
          storage_message_id: number
          title?: string | null
        }
        Update: {
          created_at?: string
          episode_number?: number
          file_id?: string
          file_size?: number | null
          file_unique_id?: string
          id?: string
          movie_id?: string
          season_number?: number
          storage_chat_id?: number
          storage_message_id?: number
          title?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "series_episodes_movie_id_fkey"
            columns: ["movie_id"]
            isOneToOne: false
            referencedRelation: "movies"
            referencedColumns: ["id"]
          },
        ]
      }
      upload_sessions: {
        Row: {
          draft: Json
          step: string
          telegram_user_id: number
          updated_at: string
        }
        Insert: {
          draft?: Json
          step: string
          telegram_user_id: number
          updated_at?: string
        }
        Update: {
          draft?: Json
          step?: string
          telegram_user_id?: number
          updated_at?: string
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
    }
    Enums: {
      app_role: "admin" | "user"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      app_role: ["admin", "user"],
    },
  },
} as const
